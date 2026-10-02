"""ILM → standalone editor hand-off helpers (no Qt).

ILM's ``MainWindow._open_plot_editor_dialog`` calls
``PlotEditorWindow(doc, for_ilm=True).exec()``; the adapter launches the
standalone process and passes a real document through a temp
``--ilm-copy`` file. The cell's store file is immutable and is never
written back.
"""

import os
import shutil
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


def is_ilm_store_file(path):
    """True for files inside ILM's immutable content-addressed store.

    Anything we cannot verify (import/lookup failure) is treated as a
    store file — the safe default is copy, never overwrite.
    """
    try:
        from src.utils.editable_plot import plot_documents_root
        root = os.path.realpath(plot_documents_root())
    except Exception:
        return True
    target = os.path.realpath(path)
    try:
        return os.path.normcase(
            os.path.commonpath([target, root])) == os.path.normcase(root)
    except ValueError:
        return False


def copy_ilm_source(source_path):
    """Copy the source file verbatim into the ILM-copy temp subdir."""
    directory = _ilm_copy_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, uuid.uuid4().hex + '.ilmplot.svg')
    shutil.copyfile(source_path, path)
    return path


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


def is_native_plot_path(path):
    """True for an existing local ``*.ilmplot.svg`` file."""
    return bool(path) and os.path.isfile(path) \
        and path.lower().endswith('.ilmplot.svg')
