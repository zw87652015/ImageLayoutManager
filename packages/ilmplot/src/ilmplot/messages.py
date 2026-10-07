"""User-facing messages for ilmplot — English defaults plus a hook.

ILM (or another host application) registers its translator via
:func:`set_translator` so document parsing errors surface in the
application language. Without a translator the English strings below
are used.
"""

from __future__ import annotations

_ENGLISH = {
    'err_plot_newer_schema':
        'This plot was made by a newer version of the Plot Editor '
        '(format {found}; this version reads {supported}). '
        'Update ILM to edit it.',
    'err_plot_newer_features':
        'This plot uses features from a newer version of the Plot '
        'Editor: {features}. Update ILM to edit it.',
    'err_svg_entities':
        'Unsupported SVG: entity declarations are not allowed',
}

_translator = None


def set_translator(fn):
    """Register a ``tr(key, **fmt)`` callable, or None to reset."""
    global _translator
    _translator = fn


def text(key: str, **fmt) -> str:
    """Message for *key*; translator first, English table on KeyError."""
    if _translator is not None:
        try:
            return _translator(key, **fmt)
        except KeyError:
            pass
    msg = _ENGLISH[key]
    return msg.format(**fmt) if fmt else msg
