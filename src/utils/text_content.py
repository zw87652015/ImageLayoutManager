"""Convert between stored text (TextItem.text) and the Content editor.

Qt-free. Stored text is HTML: a line break is `<br>`, and an inline edit on
canvas stores a full Qt `toHtml()` document. The editor shows plain text with
"\n" line breaks.
"""

import re
from html.parser import HTMLParser

_BR_RE = re.compile(r"<br\s*/?\s*>", re.IGNORECASE)
_DOC_RE = re.compile(r"<!doctype|<html", re.IGNORECASE)
_BLOCK_TAGS = frozenset({"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS = frozenset({"head", "style", "title", "script"})


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


class _DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[list[str]] = []
        self._current: list[str] | None = None
        self._skip = 0

    def _start_block(self):
        self._current = []
        self.blocks.append(self._current)

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif self._skip:
            return
        elif tag in _BLOCK_TAGS:
            self._start_block()
        elif tag == "br":
            if self._current is None:
                self._start_block()
            self._current.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif not self._skip and tag in _BLOCK_TAGS:
            self._current = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._current is None:
            if not data.strip():
                return
            self._start_block()
        self._current.append(data)


def _document_to_editor(text: str) -> str:
    parser = _DocumentParser()
    parser.feed(text)
    parser.close()
    lines = []
    for parts in parser.blocks:
        block = "".join(parts)
        lines.append("" if block == "\n" else block)
    return "\n".join(lines)


def stored_to_editor(stored: str) -> str:
    text = _normalize(stored)
    if _DOC_RE.search(text):
        return _document_to_editor(text)
    return _BR_RE.sub("\n", text)


def editor_to_stored(text: str) -> str:
    return _normalize(text).replace("\n", "<br>")
