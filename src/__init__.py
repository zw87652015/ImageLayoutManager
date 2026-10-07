"""ILM application package root.

When the source tree is present, the in-repo ``packages/ilmplot/src``
directory is put first on ``sys.path`` so the bundled copy of the
``ilmplot`` package always wins over any pip-installed one. In frozen
builds the directory does not exist and the packaged ``ilmplot`` module
is used instead.
"""

import os
import sys

_ILMPLOT_SRC = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'packages', 'ilmplot', 'src')
if os.path.isdir(_ILMPLOT_SRC) and _ILMPLOT_SRC not in sys.path:
    sys.path.insert(0, _ILMPLOT_SRC)
