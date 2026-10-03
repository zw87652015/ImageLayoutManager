"""User colour themes for the Plot Editor (Qt-free).

Custom themes live as one JSON file each under ``<root>`` (the
``plot_themes`` sibling of the preset root — see ``chrome.theme_root``),
``<slug>.ilmtheme.json`` with ``{"format": "ilm-plot-theme",
"schema_version": 1, "name", "colors": [hex, ...]}``. Documents and
overrides reference them as ``'custom:<name>'``; ``palettes`` resolves
the name at render time through its installed registry.
"""

import json
import os
import re

from .document import _check_color
from .presets import PresetError, _check_name, _slug, _write_atomic

FORMAT = 'ilm-plot-theme'
SCHEMA_VERSION = 1
MAX_COLORS = 64
_SUFFIX = '.ilmtheme.json'


class ThemeError(ValueError):
    pass


_HEX_RE = re.compile(
    r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}'
    r'|[0-9a-fA-F]{8})$')


def check_colors(colors):
    """Strict colour list: 1..MAX_COLORS literal hex strings."""
    if not isinstance(colors, list) \
            or not 1 <= len(colors) <= MAX_COLORS:
        raise ThemeError('colors: expected 1..%d hex strings'
                         % MAX_COLORS)
    for c in colors:
        if not isinstance(c, str) or not _HEX_RE.match(c.strip()):
            raise ThemeError('colors: expected hex strings, '
                             'got %r' % (c,))
    try:
        return [_check_color(c, 'colors') for c in colors]
    except ValueError as e:
        raise ThemeError(str(e)) from e


class Theme:
    """A named colour list; ``builtin`` themes come from THEMES."""

    def __init__(self, name, colors, builtin=False, filename=None):
        self.name = name
        self.colors = list(colors)
        self.builtin = builtin
        self.filename = filename

    def to_dict(self):
        _check_name(self.name)
        return {'format': FORMAT, 'schema_version': SCHEMA_VERSION,
                'name': self.name, 'colors': check_colors(
                    list(self.colors))}

    @classmethod
    def from_dict(cls, data, filename=None):
        if not isinstance(data, dict):
            raise ThemeError('expected a JSON object')
        for k in data:
            if k not in ('format', 'schema_version', 'name', 'colors'):
                raise ThemeError('unknown key %r' % k)
        if data.get('format') != FORMAT:
            raise ThemeError('format: expected %r' % FORMAT)
        if data.get('schema_version') != SCHEMA_VERSION:
            raise ThemeError('schema_version: expected %d'
                             % SCHEMA_VERSION)
        name = data.get('name')
        try:
            _check_name(name)
        except PresetError as e:
            raise ThemeError(str(e)) from e
        return cls(name, check_colors(data.get('colors')),
                   filename=filename)


class ThemeStore:
    """Folder-backed collection of custom themes."""

    def __init__(self, root):
        self.root = root
        self.errors = []

    def _custom(self):
        self.errors = []
        out = []
        try:
            names = sorted(os.listdir(self.root))
        except OSError:
            return out
        for fn in names:
            if not fn.lower().endswith(_SUFFIX):
                continue
            path = os.path.join(self.root, fn)
            try:
                with open(path, encoding='utf-8') as fh:
                    out.append(Theme.from_dict(json.load(fh),
                                               filename=fn))
            except (OSError, ValueError) as e:
                self.errors.append((fn, str(e)))
        out.sort(key=lambda t: t.name.lower())
        return out

    def list(self):
        """Built-ins (from ``palettes.THEMES``) then custom themes."""
        from .palettes import THEMES
        return ([Theme(name, colors, builtin=True)
                 for name, colors in THEMES.items()]
                + self._custom())

    def get(self, name):
        for t in self._custom():
            if t.name == name:
                return t
        return None

    def mapping(self):
        """``{name: colors}`` for ``palettes.set_custom_themes``."""
        return {t.name: list(t.colors) for t in self._custom()}

    def save(self, theme, overwrite=False):
        try:
            _check_name(theme.name)
        except PresetError as e:
            raise ThemeError(str(e)) from e
        existing = self.get(theme.name)
        if existing is not None and not overwrite \
                and existing.filename != theme.filename:
            raise ThemeError(
                'A theme named %r already exists' % theme.name)
        path = os.path.join(self.root, _slug(theme.name) + _SUFFIX)
        theme.filename = os.path.basename(path)
        _write_atomic(path, json.dumps(theme.to_dict(),
                                       ensure_ascii=False, indent=2))
        return theme

    def rename(self, old, new):
        t = self.get(old)
        if t is None:
            raise ThemeError('No theme named %r' % old)
        try:
            _check_name(new)
        except PresetError as e:
            raise ThemeError(str(e)) from e
        if self.get(new) is not None:
            raise ThemeError('A theme named %r already exists' % new)
        if t.filename:
            try:
                os.unlink(os.path.join(self.root, t.filename))
            except OSError:
                pass
        t.name = new
        return self.save(t, overwrite=True)

    def duplicate(self, name):
        """Copy a theme (built-ins allowed) as a new custom theme."""
        from .palettes import THEMES
        src = self.get(name)
        colors = list(src.colors) if src is not None \
            else THEMES.get(name)
        if colors is None:
            raise ThemeError('No theme named %r' % name)
        base = re.sub(r'\s*\(\d+\)$', '', name)
        for n in range(2, 1000):
            cand = '%s (%d)' % (base, n)
            if self.get(cand) is None:
                break
        return self.save(Theme(cand, colors))

    def delete(self, name):
        t = self.get(name)
        if t is None:
            raise ThemeError('No theme named %r' % name)
        try:
            os.unlink(os.path.join(self.root, t.filename))
        except OSError as e:
            raise ThemeError(str(e)) from e
