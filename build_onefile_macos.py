import os
import sys
import re
import plistlib
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

    if not entry.exists():
        print(f"Entry file not found: {entry}")
        return 1

    # Make sure imports like `from src...` work during analysis.
    src_path = str(project_root / "src")

    # Detect current architecture so the build matches the running Python.
    # Override by setting MACOS_ARCH env var to "x86_64", "arm64", or "universal2".
    import platform
    arch = os.environ.get("MACOS_ARCH", platform.machine())  # "x86_64" or "arm64"

    assets_dir = project_root / "assets"
    # PyInstaller --add-data syntax:  src:dest  (dest is relative inside bundle)
    add_data_args = []
    if assets_dir.exists():
        add_data_args.append(f"--add-data={assets_dir}:assets")

    # App icon — generate a proper multi-resolution .icns if it doesn't exist yet
    icon_icns = assets_dir / "icon.icns"
    icon_ico  = assets_dir / "icon.ico"
    if not icon_icns.exists() and icon_ico.exists():
        print("Generating assets/icon.icns from assets/icon.ico …")
        _generate_icns(icon_ico, icon_icns)

    icon_args = [f"--icon={icon_icns}"] if icon_icns.exists() else []

    args = [
        "--noconfirm",
        "--clean",
        # Do NOT use --onefile on macOS: it extracts to a temp dir at launch,
        # which breaks Python's early init (io module) and triggers macOS Gatekeeper.
        # --windowed alone produces a proper self-contained .app bundle.
        "--windowed",
        "--name=ImageLayoutManager",
        f"--paths={src_path}",
        f"--target-arch={arch}",
        # Ensure QtSvg gets bundled (used for SVG rendering of checkbox assets)
        "--collect-submodules=PyQt6.QtSvg",
        "--collect-submodules=PyQt6",
        # Pillow plugins sometimes require hidden imports
        "--collect-submodules=PIL",
        # stdlib modules that PyInstaller can miss in --windowed mode
        "--hidden-import=encodings",
        "--hidden-import=codecs",
        # imageio_ffmpeg ships a ~60 MB ffmpeg binary not used by this app
        "--exclude-module=imageio",
        "--exclude-module=imageio_ffmpeg",
        *icon_args,
        *add_data_args,
        str(entry),
    ]

    print("Running PyInstaller with args:")
    for a in args:
        print(f"  {a}")

    pyinstaller_run(args)

    dist_app = project_root / "dist" / "ImageLayoutManager.app"
    dist_bin = project_root / "dist" / "ImageLayoutManager"

    if dist_app.exists():
        # Inject metadata into Info.plist
        version_py = project_root / "src" / "version.py"
        app_version = "1.0.0"
        if version_py.exists():
            v_match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', version_py.read_text(encoding="utf-8"))
            if v_match:
                app_version = v_match.group(1)
        
        plist_path = dist_app / "Contents" / "Info.plist"
        if plist_path.exists():
            print(f"Applying metadata to {plist_path} (Version: {app_version})...")
            with open(plist_path, 'rb') as f:
                pl = plistlib.load(f)
            
            pl['CFBundleShortVersionString'] = app_version
            pl['CFBundleVersion'] = app_version
            pl['CFBundleName'] = "ImageLayoutManager"
            pl['CFBundleDisplayName'] = "ImageLayoutManager"
            pl['NSHumanReadableCopyright'] = "Copyright © 2026. All rights reserved."
            
            with open(plist_path, 'wb') as f:
                plistlib.dump(pl, f)

        print(f"\nBuild OK: {dist_app}")
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
