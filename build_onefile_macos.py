import os
import sys
import re
import plistlib
import shutil
from pathlib import Path


def _generate_icns(src: Path, dest: Path) -> bool:
    """Build a proper multi-resolution .icns from any image sips can read."""
    import subprocess
    import shutil
    import tempfile

    iconset = Path(tempfile.mkdtemp()) / "app.iconset"
    iconset.mkdir()
    try:
        # Standard macOS iconset size pairs  (logical size, actual pixels)
        pairs = [
            (16, 16), (16, 32),
            (32, 32), (32, 64),
            (64, 64), (64, 128),
            (128, 128), (128, 256),
            (256, 256), (256, 512),
            (512, 512), (512, 1024),
        ]
        names = [
            "icon_16x16.png",   "icon_16x16@2x.png",
            "icon_32x32.png",   "icon_32x32@2x.png",
            "icon_64x64.png",   "icon_64x64@2x.png",
            "icon_128x128.png", "icon_128x128@2x.png",
            "icon_256x256.png", "icon_256x256@2x.png",
            "icon_512x512.png", "icon_512x512@2x.png",
        ]
        for (_, px), name in zip(pairs, names):
            subprocess.run(
                ["sips", "-s", "format", "png",
                 "-z", str(px), str(px),
                 str(src), "--out", str(iconset / name)],
                check=True, capture_output=True,
            )
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(dest)],
            check=True, capture_output=True,
        )
        print(f"Generated {dest}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Warning: icns generation failed: {e.stderr.decode().strip()}")
        return False
    finally:
        shutil.rmtree(str(iconset.parent), ignore_errors=True)


def main() -> int:
    """Build a single-file macOS application bundle using PyInstaller.

    Usage:
        python build_onefile_macos.py

    Notes:
        - Ensure you have PyInstaller installed: pip install pyinstaller
        - Output will be placed in ./dist
        - The bundle ships two executables in Contents/MacOS:
          ``ImageLayoutManager`` (the GUI, CFBundleExecutable) and
          ``imagelayout-cli`` (the headless console CLI, mirroring the
          Windows ``imagelayout-cli.exe``). Both share one
          Contents/Frameworks / Contents/Resources via a generated spec
          file (two EXE entries -> one COLLECT -> one BUNDLE; the GUI
          EXE must stay first in the COLLECT because BUNDLE picks the
          first executable as CFBundleExecutable).
        - On macOS, --windowed produces a .app bundle; --onefile wraps it
          into a single self-extracting binary alongside the .app.
        - To code-sign the result, run:
              codesign --deep --force --sign "-" dist/ImageLayoutManager.app
    """

    if sys.platform != "darwin":
        print("This script is intended for macOS only.")
        print(f"Current platform: {sys.platform}")
        return 1

    try:
        from PyInstaller.__main__ import run as pyinstaller_run
    except Exception as e:
        print("PyInstaller is not installed or failed to import.")
        print("Install it with: pip install pyinstaller")
        print(f"Import error: {e}")
        return 1

    project_root = Path(__file__).resolve().parent
    entry = project_root / "main.py"
    cli_entry = project_root / "cli_main.py"

    if not entry.exists():
        print(f"Entry file not found: {entry}")
        return 1
    if not cli_entry.exists():
        print(f"CLI entry file not found: {cli_entry}")
        return 1

    # Make sure imports like `from src...` work during analysis.
    src_path = str(project_root / "src")
    ilmplot_path = str(project_root / "packages" / "ilmplot" / "src")

    # Detect current architecture so the build matches the running Python.
    # Override by setting MACOS_ARCH env var to "x86_64", "arm64", or "universal2".
    import platform
    arch = os.environ.get("MACOS_ARCH", platform.machine())  # "x86_64" or "arm64"

    assets_dir = project_root / "assets"
    from build_licenses import prepare_licenses
    legal_dir = prepare_licenses(project_root)
    spec_datas = [(str(legal_dir), "licenses")]
    if assets_dir.exists():
        spec_datas.append((str(assets_dir), "assets"))
    docs_dir = project_root / "docs"
    # src/agent/tool_specs.py reads docs/agent_concepts.md relative to
    # _MEIPASS, and the CLI's `mcp` verb serves it over ilm://concepts.
    if docs_dir.exists():
        spec_datas.append((str(docs_dir), "docs"))

    # App icon — generate a proper multi-resolution .icns if it doesn't exist yet
    icon_icns = assets_dir / "icon.icns"
    icon_ico  = assets_dir / "icon.ico"
    if not icon_icns.exists() and icon_ico.exists():
        print("Generating assets/icon.icns from assets/icon.ico …")
        _generate_icns(icon_ico, icon_icns)

    icns_arg = repr(str(icon_icns)) if icon_icns.exists() else "None"

    # Two executables in one .app can't be expressed with PyInstaller CLI
    # args, so generate a spec file: two Analysis objects (same settings),
    # two EXE entries, one COLLECT, one BUNDLE. BUNDLE places every
    # EXECUTABLE from the COLLECT into Contents/MacOS and picks the FIRST
    # as CFBundleExecutable — the GUI EXE must stay first.
    # Do NOT use --onefile-style self-extraction on macOS: it extracts to a
    # temp dir at launch, which breaks Python's early init (io module) and
    # triggers macOS Gatekeeper.
    spec_path = project_root / "build" / "ImageLayoutManager-macos.spec"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(f"""\
# Generated by build_onefile_macos.py — do not edit by hand.
from PyInstaller.utils.hooks import collect_submodules, collect_all

hidden = (
    # Ensure QtSvg gets bundled (used for SVG rendering of checkbox assets)
    collect_submodules('PyQt6.QtSvg')
    + collect_submodules('PyQt6')
    # Pillow plugins sometimes require hidden imports
    + collect_submodules('PIL')
    + collect_submodules('websockets')
    # stdlib modules that PyInstaller can miss
    + ['encodings', 'codecs']
)

extra_datas = []
extra_binaries = []
extra_hidden = []
for _pkg in ('rapidocr', 'onnxruntime'):
    # rapidocr ships YAML configs and .onnx models as package data
    _d, _b, _h = collect_all(_pkg)
    extra_datas += _d
    extra_binaries += _b
    extra_hidden += _h
hidden += extra_hidden

_common = dict(
    pathex=[{src_path!r}, {ilmplot_path!r}],
    binaries=extra_binaries,
    datas={spec_datas!r} + extra_datas,
    hiddenimports=hidden,
    # imageio_ffmpeg ships a ~60 MB ffmpeg binary not used by this app
    excludes=['imageio', 'imageio_ffmpeg'],
)

a_gui = Analysis([{str(entry)!r}], **_common)
a_cli = Analysis([{str(cli_entry)!r}], **_common)

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

gui_exe = EXE(
    pyz_gui,
    a_gui.scripts,
    name='ImageLayoutManager',
    console=False,
    exclude_binaries=True,
    target_arch={arch!r},
    icon={icns_arg},
    upx=False,
)
cli_exe = EXE(
    pyz_cli,
    a_cli.scripts,
    name='imagelayout-cli',
    console=True,
    exclude_binaries=True,
    target_arch={arch!r},
    upx=False,
)

coll = COLLECT(
    gui_exe,
    cli_exe,
    a_gui.binaries,
    a_gui.datas,
    a_cli.binaries,
    a_cli.datas,
    name='ImageLayoutManager',
    upx=False,
)

# COLLECT inherits `console` from its LAST EXE (the console CLI), and
# BUNDLE turns console=True into LSBackgroundOnly=True (no Dock icon, no
# menu bar) and drops NSHighResolutionCapable. Override both explicitly.
app = BUNDLE(
    coll,
    name='ImageLayoutManager.app',
    icon={icns_arg},
    info_plist={{'LSBackgroundOnly': False, 'NSHighResolutionCapable': True}},
)
""", encoding="utf-8")

    print(f"Wrote spec: {spec_path}")

    pyinstaller_run([
        str(spec_path),
        "--noconfirm",
        "--clean",
        f"--distpath={project_root / 'dist'}",
        f"--workpath={project_root / 'build'}",
    ])

    dist_app = project_root / "dist" / "ImageLayoutManager.app"
    dist_bin = project_root / "dist" / "ImageLayoutManager"

    if dist_app.exists():
        # Inject metadata into Info.plist
        version_py = project_root / "src" / "version.py"
        version_text = version_py.read_text(encoding="utf-8") if version_py.exists() else ""

        def _grab(field: str, default: str) -> str:
            m = re.search(rf'{field}\s*=\s*["\']([^"\']+)["\']', version_text)
            return m.group(1) if m else default

        app_version = _grab("APP_VERSION", "1.0.0")
        publisher = _grab("APP_PUBLISHER", "zw87652015")
        year = _grab("APP_COPYRIGHT_YEAR", "2026")
        license_str = _grab("APP_LICENSE", "Apache-2.0")
        copyright_str = (
            f"Copyright (C) {year} {publisher}. Licensed under {license_str}."
        )

        plist_path = dist_app / "Contents" / "Info.plist"
        if plist_path.exists():
            print(f"Applying metadata to {plist_path} (Version: {app_version})...")
            with open(plist_path, 'rb') as f:
                pl = plistlib.load(f)

            pl['CFBundleShortVersionString'] = app_version
            pl['CFBundleVersion'] = app_version
            pl['CFBundleName'] = "ImageLayoutManager"
            pl['CFBundleDisplayName'] = "ImageLayoutManager"
            pl['NSHumanReadableCopyright'] = copyright_str
            pl['CFBundleDocumentTypes'] = [
                {
                    'CFBundleTypeName': 'Academic Figure Layout',
                    'CFBundleTypeRole': 'Editor',
                    'LSHandlerRank': 'Owner',
                    'LSItemContentTypes': ['com.imagelayoutmanager.figlayout'],
                    'CFBundleTypeExtensions': ['figlayout'],
                    'CFBundleTypeIconFile': 'icon',
                },
                {
                    'CFBundleTypeName': 'Academic Figure Bundle',
                    'CFBundleTypeRole': 'Editor',
                    'LSHandlerRank': 'Owner',
                    'LSItemContentTypes': ['com.imagelayoutmanager.figpack'],
                    'CFBundleTypeExtensions': ['figpack'],
                    'CFBundleTypeIconFile': 'icon_figpack',
                },
            ]
            pl['UTExportedTypeDeclarations'] = [
                {
                    'UTTypeIdentifier': 'com.imagelayoutmanager.figlayout',
                    'UTTypeDescription': 'Academic Figure Layout',
                    'UTTypeConformsTo': ['public.data'],
                    'UTTypeTagSpecification': {'public.filename-extension': ['figlayout']},
                },
                {
                    'UTTypeIdentifier': 'com.imagelayoutmanager.figpack',
                    'UTTypeDescription': 'Academic Figure Bundle',
                    'UTTypeConformsTo': ['public.zip-archive'],
                    'UTTypeTagSpecification': {'public.filename-extension': ['figpack']},
                },
            ]
            
            with open(plist_path, 'wb') as f:
                plistlib.dump(pl, f)

        # Ship license texts inside the bundle (required for the bundled
        # GPLv3 (PyQt6) / AGPL-3.0 (PyMuPDF) components — see NOTICE).
        resources_dir = dist_app / "Contents" / "Resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        for legal_name in ("LICENSE", "NOTICE"):
            legal_src = project_root / legal_name
            if legal_src.exists():
                shutil.copy2(legal_src, resources_dir / legal_name)

        cli_bin = dist_app / "Contents" / "MacOS" / "imagelayout-cli"
        if not cli_bin.exists():
            print("Build finished, but the bundled CLI executable is missing:")
            print(f"  {cli_bin}")
            return 2

        with open(plist_path, 'rb') as f:
            final_pl = plistlib.load(f)
        if final_pl.get('LSBackgroundOnly') or not final_pl.get('NSHighResolutionCapable'):
            print("Info.plist marks the GUI as background-only or non-HiDPI "
                  "(it would open with no Dock icon or menu bar):")
            print(f"  {plist_path}")
            return 2

        print(f"\nBuild OK: {dist_app}")
        print(f"Bundled CLI: {cli_bin}")
        print("To ad-hoc sign (required to run on macOS 10.15+):")
        print(f'  codesign --deep --force --sign "-" "{dist_app}"')
        return 0

    if dist_bin.exists():
        print(f"Build OK: {dist_bin}")
        return 0

    print("Build finished, but the output was not found at expected paths:")
    print(f"  {dist_app}")
    print(f"  {dist_bin}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
