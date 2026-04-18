import os
import sys
from pathlib import Path


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
