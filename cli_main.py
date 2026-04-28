"""PyInstaller / dev entry point for ``imagelayout-cli.exe``.

Mirrors the DLL-fix prelude in ``main.py`` so the bundled binary can
locate Qt's runtime DLLs in both ``--onefile`` and ``--onedir``
layouts on Windows. Then dispatches to ``src.cli.main:main``.
"""
import os
import sys

# --- DLL Path Fix for PyInstaller + PyQt6 on Windows ---
if getattr(sys, "frozen", False) and sys.platform == "win32":
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    dll_dirs = [
        base_dir,
        os.path.join(base_dir, "_internal"),
        os.path.join(base_dir, "PyQt6", "Qt6", "bin"),
        os.path.join(base_dir, "_internal", "PyQt6", "Qt6", "bin"),
    ]
    existing_path = os.environ.get("PATH", "")
    new_paths = [d for d in dll_dirs if os.path.isdir(d)]
    if new_paths:
        os.environ["PATH"] = ";".join(new_paths) + ";" + existing_path
    if hasattr(os, "add_dll_directory"):
        for d in new_paths:
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
# -------------------------------------------------------

# Add src to python path (matches main.py behaviour) so ``import src.…``
# works whether we're running from the repo root or a frozen bundle.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from src.cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
