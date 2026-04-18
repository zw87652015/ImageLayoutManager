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

    # PyQt6 modules actually used by this application.
    # Do NOT add "--collect-submodules=PyQt6" (no qualifier) — that pulls in
    # every Qt6 addon (WebEngine, Multimedia, Bluetooth, 3D, SQL, …) and adds
    # hundreds of MB to the exe for no benefit.
    used_qt_modules = [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtSvg",
    ]

    # Qt6 addons that are definitely NOT used — exclude them so PyInstaller
    # does not pull them in transitively.
    unused_qt_modules = [
        "PyQt6.QtNetwork",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebChannel",
        "PyQt6.Qt3DCore",
        "PyQt6.Qt3DRender",
        "PyQt6.Qt3DInput",
        "PyQt6.Qt3DLogic",
        "PyQt6.Qt3DAnimation",
        "PyQt6.Qt3DExtras",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.QtPositioning",
        "PyQt6.QtLocation",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtXml",
        # numpy: not used by this app
        "numpy",
        # imageio / imageio_ffmpeg: scientific packages present in conda envs;
        # imageio_ffmpeg ships a ~60 MB ffmpeg binary — exclude both.
        "imageio",
        "imageio_ffmpeg",
    ]

    assets_dir = project_root / "assets"
    icon_path = assets_dir / "icon.ico"

    args = [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name=ImageLayoutManager",
        f"--paths={src_path}",
        # UPX compression causes "Failed to extract LIBBZ2.dll / return code -1"
        # on some Windows machines because UPX's decompressor is unreliable with
        # certain Qt/bzip2 DLLs. Keeping the exe uncompressed avoids the crash.
        "--noupx",
        # Extract to the exe's own directory instead of %TEMP% — prevents Windows
        # Defender from blocking Qt DLLs written to system temp folders.
        "--runtime-tmpdir=.",
    ]

    if icon_path.exists():
        args.append(f"--icon={icon_path}")

    if assets_dir.exists():
        args.append(f"--add-data={assets_dir};assets")

    for mod in used_qt_modules:
        args.append(f"--collect-submodules={mod}")

    for mod in unused_qt_modules:
        args.append(f"--exclude-module={mod}")

    args.append(str(entry))


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
