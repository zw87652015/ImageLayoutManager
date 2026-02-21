import os
import sys
import subprocess
from pathlib import Path


def main() -> int:
    """Build a standalone Windows executable using Nuitka.

    Usage:
        python build_nuitka.py

    Prerequisites:
        pip install nuitka ordered-set zstandard
        A C compiler must be available (MSVC via Visual Studio, or MinGW64).
        Nuitka will offer to download MinGW64 automatically if none is found.

    Notes:
        - Nuitka compiles Python to C, producing a native executable.
        - Startup is significantly faster than PyInstaller --onefile.
        - Output will be placed in ./build/ImageLayoutManager.dist/
    """

    # Check nuitka is importable
    try:
        import nuitka  # noqa: F401
    except ImportError:
        print("Nuitka is not installed.")
        print("Install it with:  pip install nuitka ordered-set zstandard")
        return 1

    project_root = Path(__file__).resolve().parent
    entry = project_root / "main.py"

    if not entry.exists():
        print(f"Entry file not found: {entry}")
        return 1

    cmd = [
        sys.executable, "-m", "nuitka",

        # ── Output mode ──────────────────────────────────────────────
        "--standalone",                     # bundle everything into a folder
        "--onefile",                        # then pack into a single exe
        "--onefile-tempdir-spec={CACHE_DIR}/ImageLayoutManager",
        # ^ reuse extracted cache across launches → near-instant 2nd start

        # ── Identity ─────────────────────────────────────────────────
        "--output-filename=ImageLayoutManager.exe",
        "--output-dir=dist_nuitka",
        "--windows-console-mode=disable",   # GUI app, no console

        # ── Qt plugin ────────────────────────────────────────────────
        "--enable-plugin=pyqt6",

        # ── Packages to include ──────────────────────────────────────
        "--include-package=src",
        "--include-module=PIL",
        "--include-module=numpy",

        # PyMuPDF (fitz) is imported lazily; make sure it's bundled
        "--include-module=fitz",
    ]

    # ── Windows icon (requires ICO format) ──
    icon_path = project_root / "assets" / "icon.ico"
    if icon_path.exists():
        cmd.extend([f"--windows-icon-from-ico={icon_path}"])
    else:
        # Fallback: try PNG if ICO not available
        png_icon = project_root / "assets" / "icon.png"
        if png_icon.exists():
            cmd.extend([f"--windows-icon-from-ico={png_icon}"])

    # ── Data files ───────────────────────────────────────────────
    # Include assets folder for runtime access
    assets_path = project_root / "assets"
    if assets_path.exists():
        cmd.append(f"--include-data-dir={assets_path}=assets")

    # ── Optimisation ─────────────────────────────────────────────
    cmd.extend([
        "--assume-yes-for-downloads",       # auto-download MinGW if needed
        "--remove-output",                  # clean previous build artifacts
        "--jobs=4",                         # parallel C compilation
        str(entry),
    ])

    print("Running Nuitka with command:")
    print(" ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=str(project_root))

    if result.returncode != 0:
        print(f"\nNuitka build failed with exit code {result.returncode}")
        return result.returncode

    dist_exe = project_root / "dist_nuitka" / "ImageLayoutManager.exe"
    if dist_exe.exists():
        print(f"\nBuild OK: {dist_exe}")
        print(f"Size: {dist_exe.stat().st_size / (1024*1024):.1f} MB")
        return 0

    print("\nBuild finished, but executable was not found at expected path:")
    print(f"  {dist_exe}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
