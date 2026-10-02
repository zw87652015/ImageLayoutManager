"""ILM → standalone editor hand-off helpers (no Qt).

ILM's ``MainWindow._open_plot_editor_dialog`` calls
``PlotEditorWindow(doc, for_ilm=True).exec()``; the adapter launches the
standalone process and passes a real document through a temp
``--ilm-copy`` file. The cell's store file is immutable and is never
written back.
"""

import os
import tempfile
import uuid

from .document import PlotDocument
from .render import save_document

_TEMP_SUBDIR = 'ilm-plot-editor'


def _is_default_document(doc):
    """True when *doc* differs from ``PlotDocument()`` only in size/ids."""
    if not isinstance(doc, PlotDocument):
        return False
    a = doc.to_dict()
    b = PlotDocument().to_dict()
    a.pop('width_mm', None)
    a.pop('height_mm', None)
    b.pop('width_mm', None)
    b.pop('height_mm', None)
    sa = [{k: v for k, v in s.items() if k != 'id'}
          for s in a.get('series', [])]
    sb = [{k: v for k, v in s.items() if k != 'id'}
          for s in b.get('series', [])]
    return a.get('series') is not None and sa == sb and \
        {k: v for k, v in a.items() if k != 'series'} == \
        {k: v for k, v in b.items() if k != 'series'}


def _ilm_copy_dir():
    return os.path.join(tempfile.gettempdir(), _TEMP_SUBDIR)


def write_ilm_copy(doc):
    """Write *doc* to a fresh temp ``*.ilmplot.svg``; returns the path."""
    directory = _ilm_copy_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, uuid.uuid4().hex + '.ilmplot.svg')
    save_document(doc, path)
    return path


def is_ilm_copy_path(path):
    """True only for paths directly inside the ILM-copy temp subdir."""
    directory = os.path.normcase(os.path.abspath(_ilm_copy_dir()))
    parent = os.path.normcase(os.path.abspath(os.path.dirname(path)))
    return parent == directory
