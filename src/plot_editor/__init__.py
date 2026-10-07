"""ILM Plot Editor — standalone editable line-plot documents.

The native document is a self-contained SVG (``*.ilmplot.svg``) that embeds
a versioned JSON payload inside ``<metadata id="ilm-plot-document">`` so the
same file is both the vector snapshot and the editable source of truth.

The Qt- and ILM-free core lives in the ``ilmplot`` package
(``packages/ilmplot``); ``document``/``render``/``stats``/``mathtext``/
``matplotlib_bridge`` here are compatibility aliases for
``ilmplot.document``/``ilmplot.render``/``ilmplot.stats``/
``ilmplot.mathtext``/``ilmplot.bridge``. UI modules live in
:mod:`src.plot_editor.window` / :mod:`src.plot_editor.app`.
"""

import ilmplot.messages

from . import i18n

ilmplot.messages.set_translator(i18n.tr)


def _ilmplot_message_keys():
    """Literal references for the keys ilmplot translates through the
    registered hook — keeps the editor's unused-key audit aware that the
    strings still belong to this table."""
    tr = i18n.tr
    return (tr('err_plot_newer_schema', found=0, supported=0),
            tr('err_plot_newer_features', features=''),
            tr('err_svg_entities'))
