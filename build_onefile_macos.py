import argparse
import hashlib
import json
import os
import sys
import re
import plistlib
import shutil
import subprocess
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


def _run(cmd: list) -> subprocess.CompletedProcess:
    """Run a command, printing the command and its output on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"Command failed ({proc.returncode}): {' '.join(str(c) for c in cmd)}")
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr)
    return proc


_MACHO_MAGICS = {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                 b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
                 b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def _is_macho(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) in _MACHO_MAGICS
    except OSError:
        return False


def _sign_app(app: Path, identity: str | None) -> bool:
    """Re-seal the outer bundle after the post-build Info.plist/license edits.

    Nested code is already signed by PyInstaller, so no --deep here.
    """
    if identity:
        cmd = ["codesign", "--force", "--timestamp", "--options", "runtime",
               "--sign", identity, str(app)]
    else:
        cmd = ["codesign", "--force", "--sign", "-", str(app)]
    return _run(cmd).returncode == 0


def _verify_signature(app: Path, identity: str | None) -> list[str]:
    """Return a list of signature problems (empty = OK)."""
    problems = []
    proc = _run(["codesign", "--verify", "--deep", "--strict",
                 "--verbose=2", str(app)])
    if proc.returncode != 0:
        problems.append(f"{app}: codesign --verify failed")

    if identity:
        for target in (app, app / "Contents" / "MacOS" / "imagelayout-cli"):
            disp = _run(["codesign", "--display", "--verbose=4", str(target)])
            out = disp.stdout + disp.stderr
            if disp.returncode != 0:
                problems.append(f"{target}: codesign --display failed")
                continue
            if "Authority=Developer ID Application" not in out:
                problems.append(f"{target}: not signed with a Developer ID Application certificate")
            team = next((l for l in out.splitlines()
                         if l.startswith("TeamIdentifier=")), "")
            if not team or team == "TeamIdentifier=not set":
                problems.append(f"{target}: TeamIdentifier not set")
            flags = next((l for l in out.splitlines()
                          if l.startswith("CodeDirectory v=")), "")
            if "(runtime)" not in flags:
                problems.append(f"{target}: hardened runtime flag missing")

        contents = app / "Contents"
        for dirpath, dirnames, filenames in os.walk(contents, followlinks=False):
            for name in filenames:
                p = Path(dirpath) / name
                if p.is_symlink() or not _is_macho(p):
                    continue
                disp = _run(["codesign", "--display", "--verbose=2", str(p)])
                out = disp.stdout + disp.stderr
                if disp.returncode != 0:
                    problems.append(f"{p.relative_to(app)}: unsigned Mach-O")
                elif "Signature=adhoc" in out:
                    problems.append(f"{p.relative_to(app)}: ad-hoc signed Mach-O")
    return problems


def _notarize(app: Path, profile: str, work_dir: Path) -> bool:
    """Submit the app to Apple notarization, staple the ticket, verify with spctl."""
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    zip_path = work_dir / "ImageLayoutManager-notarize.zip"
    if _run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
             str(app), str(zip_path)]).returncode != 0:
        return False

    proc = _run(["xcrun", "notarytool", "submit", str(zip_path),
                 "--keychain-profile", profile, "--wait",
                 "--output-format", "json"])
    if proc.returncode != 0:
        return False
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"Could not parse notarytool output:\n{proc.stdout}")
        return False
    submission_id = result.get("id")
    status = result.get("status")

    if submission_id:
        log_path = work_dir / "notary-log.json"
        if _run(["xcrun", "notarytool", "log", submission_id,
                 "--keychain-profile", profile,
                 str(log_path)]).returncode == 0:
            print(f"Notary log saved: {log_path}")

    if status != "Accepted":
        print(f"Notarization failed: status={status!r}")
        return False

    if _run(["xcrun", "stapler", "staple", str(app)]).returncode != 0:
        return False
    if _run(["xcrun", "stapler", "validate", str(app)]).returncode != 0:
        return False
    assess = _run(["spctl", "--assess", "--type", "execute",
                   "--verbose=4", str(app)])
    out = assess.stdout + assess.stderr
    if assess.returncode != 0 or "accepted" not in out \
            or "Notarized Developer ID" not in out:
        print(f"Gatekeeper assessment failed:\n{out}")
        return False
    return True


def _find_identity(identity: str) -> bool:
    proc = _run(["security", "find-identity", "-v", "-p", "codesigning"])
    return proc.returncode == 0 and identity in proc.stdout


def main(argv=None) -> int:
    """Build a single-file macOS application bundle using PyInstaller.

    Usage:
        python build_onefile_macos.py [--codesign-identity NAME]
                                      [--bundle-id ID] [--notary-profile NAME]

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
        - To code-sign, pass ``--codesign-identity "Developer ID
          Application: …"`` (or set MACOS_CODESIGN_IDENTITY); the identity
          is handed to PyInstaller so all nested binaries get hardened
          runtime + timestamp, and the outer bundle is re-sealed after
          the Info.plist/license edits. ``--bundle-id`` (or
          MACOS_BUNDLE_ID) sets CFBundleIdentifier. With a
          ``notarytool`` keychain profile via ``--notary-profile`` (or
          MACOS_NOTARY_PROFILE) the app is also notarized, stapled and
          zipped into ``dist/``. Without an identity the bundle is
          ad-hoc re-signed (local use only).
    """

    if sys.platform != "darwin":
        print("This script is intended for macOS only.")
        print(f"Current platform: {sys.platform}")
        return 1

    parser = argparse.ArgumentParser(
        description="Build the macOS .app bundle for ImageLayoutManager.")
    parser.add_argument("--codesign-identity",
                        default=os.environ.get("MACOS_CODESIGN_IDENTITY"),
                        help="Signing identity (e.g. 'Developer ID Application: "
                             "Name (TEAMID)' or its SHA-1); default ad-hoc.")
    parser.add_argument("--bundle-id",
                        default=os.environ.get("MACOS_BUNDLE_ID")
                        or "com.zw87652015.imagelayoutmanager",
                        help="CFBundleIdentifier for the .app bundle.")
    parser.add_argument("--notary-profile",
                        default=os.environ.get("MACOS_NOTARY_PROFILE"),
                        help="notarytool keychain profile used to notarize "
                             "the signed app.")
    args = parser.parse_args(argv)

    identity = args.codesign_identity or None
    if args.notary_profile and not identity:
        print("Error: --notary-profile requires a code-signing identity "
              "(--codesign-identity or MACOS_CODESIGN_IDENTITY).")
        return 1

    if identity:
        if not _find_identity(identity):
            print(f"Error: signing identity not found in the keychain: {identity}")
            print("Available identities:")
            _run(["security", "find-identity", "-v", "-p", "codesigning"])
            return 1
        os.environ["PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR"] = "1"

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
    codesign_identity={identity!r},
)
cli_exe = EXE(
    pyz_cli,
    a_cli.scripts,
    name='imagelayout-cli',
    console=True,
    exclude_binaries=True,
    target_arch={arch!r},
    upx=False,
    codesign_identity={identity!r},
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
    bundle_identifier={args.bundle_id!r},
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

        # The plist/license edits above invalidated the signature PyInstaller
        # applied, so re-seal the outer bundle (nested code stays signed).
        if not _sign_app(dist_app, identity):
            print("Failed to sign the app bundle.")
            return 2

        problems = _verify_signature(dist_app, identity)
        if problems:
            print("Signature verification found problems:")
            for p in problems:
                print(f"  - {p}")
            return 2

        print(f"\nBuild OK: {dist_app}")
        print(f"Bundled CLI: {cli_bin}")

        if args.notary_profile:
            notary_dir = project_root / "build" / "notarize"
            if not _notarize(dist_app, args.notary_profile, notary_dir):
                return 2
            problems = _verify_signature(dist_app, identity)
            if problems:
                print("Signature verification found problems after stapling:")
                for p in problems:
                    print(f"  - {p}")
                return 2
            zip_name = f"ImageLayoutManager_v{app_version}_macOS_{arch}.zip"
            release_zip = project_root / "dist" / zip_name
            if release_zip.exists():
                release_zip.unlink()
            if _run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                     str(dist_app), str(release_zip)]).returncode != 0:
                return 2
            digest = hashlib.sha256(release_zip.read_bytes()).hexdigest()
            print(f"Release zip: {release_zip}")
            print(f"SHA-256: {digest}")
            return 0

        if identity:
            print(f"\nSigned with: {identity}")
            print("The app is signed but NOT notarized — it still needs "
                  "notarization before distribution.")
            print("Create a notarytool keychain profile once:")
            print('  xcrun notarytool store-credentials "ILM-notary" '
                  "--apple-id <you@example.com> --team-id BHG2P58XCR")
            print("Then rebuild with:")
            print(f"  {Path(sys.argv[0]).name} --codesign-identity "
                  f'"{identity}" --notary-profile ILM-notary')
        else:
            print("\nAd-hoc signed only — for local use, NOT for distribution.")
            print("To sign with a Developer ID certificate:")
            print(f'  {Path(sys.argv[0]).name} --codesign-identity '
                  '"Developer ID Application: <Name> (<TEAMID>)"')
            print("Add --notary-profile <profile> to also notarize "
                  "(requires `xcrun notarytool store-credentials`).")
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
