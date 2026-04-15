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

    args = [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name=ImageLayoutManager",
        f"--paths={src_path}",
        # Ensure QtSvg gets bundled (used for SVG import/export)
        "--collect-submodules=PyQt6.QtSvg",
        "--collect-submodules=PyQt6",
        # Pillow plugins sometimes require hidden imports
        "--collect-submodules=PIL",
        # macOS: request high-resolution (Retina) display support
        "--target-arch=x86_64",  # change to arm64 on Apple Silicon, or universal2 for both
        str(entry),
    ]

    print("Running PyInstaller with args:")
    for a in args:
        print(f"  {a}")

    pyinstaller_run(args)

    # --onefile on macOS produces a Unix binary, not a .app bundle
    dist_bin = project_root / "dist" / "ImageLayoutManager"
    dist_app = project_root / "dist" / "ImageLayoutManager.app"

    if dist_bin.exists():
        print(f"Build OK: {dist_bin}")
        return 0

    if dist_app.exists():
        print(f"Build OK: {dist_app}")
        return 0

    print("Build finished, but the output was not found at expected paths:")
    print(f"  {dist_bin}")
    print(f"  {dist_app}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
