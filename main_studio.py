"""Studio skin entry point.

Launches the normal ImageLayoutManager application with the alternate
"Studio" skin installed by ``src/app/studio_skin.py``. The skin patches
``src.app.theme`` (and, for the main window, ``src.app.main_window``)
*before* any app module binds theme functions — importing this file is the
only difference from the classic ``python main.py``, which stays
completely untouched.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
sys.path.append(os.path.join(_REPO_ROOT, 'src'))

if __name__ == "__main__":
    from src.app import studio_skin
    if "--plot-editor" in sys.argv:
        studio_skin.install(patch_window=False)
        _pe_argv = [a for a in sys.argv[1:] if a != '--plot-editor']
        from src.plot_editor.app import main as _plot_main
        sys.exit(_plot_main(_pe_argv))
    studio_skin.install()
    import main as classic
    classic.main()
