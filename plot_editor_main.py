"""Source-tree launcher for the standalone ILM Plot Editor.

Equivalent to ``ImageLayoutManager.exe --plot-editor`` in a frozen build —
``main.py`` dispatches the ``--plot-editor`` flag before constructing the
main window, so the same code path serves both entries.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.plot_editor.app import main

if __name__ == '__main__':
    sys.exit(main())
