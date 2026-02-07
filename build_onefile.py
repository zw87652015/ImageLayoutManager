import os
import sys
from pathlib import Path


def main() -> int:
    """Build a single-file Windows executable using PyInstaller.

    Usage:
        python build_onefile.py

    Notes:
        - Ensure you have PyInstaller installed: pip install pyinstaller
        - Output will be placed in ./dist
    """

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
        str(entry),
    ]

    print("Running PyInstaller with args:")
    for a in args:
        print(f"  {a}")

    pyinstaller_run(args)

    dist_exe = project_root / "dist" / "ImageLayoutManager.exe"
    if dist_exe.exists():
        print(f"Build OK: {dist_exe}")
        return 0

    print("Build finished, but executable was not found at expected path:")
    print(dist_exe)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
