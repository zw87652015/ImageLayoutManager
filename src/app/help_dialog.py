"""User Guide: task cards with illustrations, a spotlight tour, and searchable shortcuts.

Content lives in help_content (Qt-free); drawing in help_illustrations. The dialog only
lays out cards and emits signals: tutorial_requested (footer), show_me_requested (target
spec for the main window to flash) and tour_requested.
"""

import html

from PyQt6.QtCore import QEvent, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from src.app.help_demo_view import DemoView
from src.app.help_demos import DEMOS
from src.app.help_illustrations import draw_topic
from src.app.i18n import current_language, tr
from src.app.help_content import TOPICS, parse_chips, search, search_shortcuts

_BANNER_H = 210
_ICON_PX = 24
_TOUR_KEY = "tour"
_SHORTCUTS_KEY = "shortcuts"


def _lang_text(pair):
    return pair[1] if current_language() == "zh" else pair[0]


def _colors(widget):
    pal = widget.palette()
    return {
        "ink": pal.color(QPalette.ColorRole.Text),
        "muted": pal.color(QPalette.ColorRole.PlaceholderText),
        "accent": pal.color(QPalette.ColorRole.Highlight),
        "base": pal.color(QPalette.ColorRole.Base),
        "surface": pal.color(QPalette.ColorRole.AlternateBase),
        "mid": pal.color(QPalette.ColorRole.Mid),
    }


def _icon_pixmap(key, px, widget):
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_topic(key, painter, QRectF(0, 0, px, px), _colors(widget))
    painter.end()
    return pixmap


def _chip_html(text, colors):
    """Rich text where [chips] become non-wrapping key caps."""
    surface = colors["surface"].name()
    ink = colors["ink"].name()
    mid = colors["mid"].name()
    out = []
    for segment, is_chip in parse_chips(text):
        if is_chip:
            body = html.escape(segment).replace(" ", "&nbsp;")
            out.append(
                f'<span style="font-family:monospace; background-color:{surface}; '
                f'color:{ink}; border:1px solid {mid};">&nbsp;{body}&nbsp;</span>'
            )
        else:
            out.append(html.escape(segment))
    return "".join(out)


class _Banner(QWidget):
    def __init__(self, key, parent=None):
        super().__init__(parent)
        self._key = key
        self.setFixedHeight(_BANNER_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = _colors(self)
        surface = QColor(colors["surface"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(surface)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, -1, -1), 10, 10)
        inner = QRectF(self.rect()).adjusted(40, 18, -40, -18)
        draw_topic(self._key, painter, inner, colors)
        painter.end()


_BADGE_STYLE = "border-radius: 12px; background: palette({role}); color: palette(base); font-weight: 600;"


class _StepRow(QWidget):
    def __init__(self, number, text, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self._badge = QLabel(str(number))
        badge = self._badge
        badge.setFixedSize(QSize(24, 24))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(_BADGE_STYLE.format(role="highlight"))
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        body = QLabel(_chip_html(text, _colors(self)))
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        row.addWidget(body, 1)

    def set_active(self, active):
        """None: normal. True: accent badge (the step now playing). False: muted badge."""
        role = "mid" if active is False else "highlight"
        self._badge.setStyleSheet(_BADGE_STYLE.format(role=role))


class _TopicCard(QWidget):
    show_me_requested = pyqtSignal(object)

    def __init__(self, topic, parent=None):
        super().__init__(parent)
        self.topic = topic
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)
        if topic.key in DEMOS:
            demo = DemoView(DEMOS[topic.key])
            demo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            demo.setFixedHeight(_BANNER_H)
            demo.step_changed.connect(self._on_demo_step)
            layout.addWidget(demo)
        else:
            layout.addWidget(_Banner(topic.icon))

        title = QLabel(_lang_text(topic.title))
        font = QFont(title.font())
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setWeight(QFont.Weight.DemiBold)
        title.setFont(font)
        title.setWordWrap(True)
        layout.addWidget(title)

        self._step_rows = []
        for number, step in enumerate(topic.steps, start=1):
            row = _StepRow(number, _lang_text(step))
            self._step_rows.append(row)
            layout.addWidget(row)

        if topic.show_me is not None:
            show = QPushButton(tr("help_show_me"))
            show.setDefault(True)
            show.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            show.clicked.connect(lambda: self.show_me_requested.emit(self.topic.show_me))
            layout.addWidget(show, 0, Qt.AlignmentFlag.AlignLeft)

        if topic.details:
            self._toggle = QPushButton(tr("help_more_details") + "  \u25b8")
            self._toggle.setFlat(True)
            self._toggle.setCheckable(True)
            self._toggle.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            self._toggle.toggled.connect(self._set_details)
            layout.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)
            bullets = "<br>".join("\u2022 " + html.escape(_lang_text(item)) for item in topic.details)
            self._details = QLabel(bullets)
            self._details.setTextFormat(Qt.TextFormat.RichText)
            self._details.setWordWrap(True)
            self._details.setContentsMargins(8, 0, 0, 0)
            self._details.hide()
            layout.addWidget(self._details)
        layout.addStretch(1)

    def _set_details(self, shown):
        self._details.setVisible(shown)
        suffix = "  \u25be" if shown else "  \u25b8"
        label = tr("help_fewer_details") if shown else tr("help_more_details")
        self._toggle.setText(label + suffix)

    def _on_demo_step(self, step):
        for number, row in enumerate(self._step_rows, start=1):
            if step == 0:
                row.set_active(None)
            else:
                row.set_active(True if number == step else False)


class _ShortcutsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)
        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(18, 14, 18, 14)
        self._layout.setSpacing(6)
        self._scroll.setWidget(self._content)
        self.set_query("")

    def set_query(self, query):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        groups = search_shortcuts(query)
        if not groups:
            self._layout.addWidget(QLabel(tr("help_no_results")))
        colors = _colors(self)
        for title, entries in groups:
            heading = QLabel(_lang_text(title))
            font = QFont(heading.font())
            font.setWeight(QFont.Weight.DemiBold)
            heading.setFont(font)
            self._layout.addWidget(heading)
            for key, (en, zh) in entries:
                row = QHBoxLayout()
                chip = QLabel(_chip_html(f"[{key}]", colors))
                chip.setTextFormat(Qt.TextFormat.RichText)
                chip.setMinimumWidth(170)
                chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
                row.addWidget(chip)
                description = QLabel(zh if current_language() == "zh" else en)
                description.setWordWrap(True)
                row.addWidget(description, 1)
                holder = QWidget()
                holder.setLayout(row)
                self._layout.addWidget(holder)
        self._layout.addStretch(1)


class _TourCard(QWidget):
    tour_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)
        layout.addWidget(_Banner(_TOUR_KEY))
        title = QLabel(tr("help_tour_title"))
        font = QFont(title.font())
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setWeight(QFont.Weight.DemiBold)
        title.setFont(font)
        layout.addWidget(title)
        text = QLabel(tr("help_tour_card_text"))
        text.setWordWrap(True)
        layout.addWidget(text)
        start = QPushButton(tr("help_tour_start"))
        start.setDefault(True)
        start.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        start.clicked.connect(self.tour_requested.emit)
        layout.addWidget(start, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


class HelpDialog(QDialog):
    tutorial_requested = pyqtSignal(str)
    show_me_requested = pyqtSignal(object)
    tour_requested = pyqtSignal()

    def __init__(self, parent=None, topic=None):
        super().__init__(parent)
        self.setWindowTitle(tr("help_title"))
        self.resize(880, 600)
        self.setMinimumSize(720, 480)
        self.setModal(False)
        self._topic_pages = {}
        self._build_ui()
        self.open_topic(topic or "first_figure")

    # ── layout ───────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(0)
        columns = QHBoxLayout()
        columns.setContentsMargins(12, 12, 12, 0)
        columns.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("help_search_placeholder"))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)
        self._search.returnPressed.connect(self._open_first_match)
        self._search.installEventFilter(self)
        left.addWidget(self._search)
        self._list = QListWidget()
        self._list.setFixedWidth(240)
        self._list.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self._list.currentItemChanged.connect(self._show_item)
        left.addWidget(self._list, 1)
        self._no_results = QLabel(tr("help_no_results"))
        self._no_results.setWordWrap(True)
        self._no_results.hide()
        left.addWidget(self._no_results)
        columns.addLayout(left)

        self._stack = QStackedWidget()
        self._tour_card = _TourCard()
        self._tour_card.tour_requested.connect(self.tour_requested.emit)
        self._shortcuts_page = _ShortcutsPage()
        self._stack.addWidget(self._tour_card)
        self._stack.addWidget(self._shortcuts_page)
        self._add_topic_pages()
        columns.addWidget(self._stack, 1)
        root.addLayout(columns, 1)

        self._list_items = {}
        self._add_list_items()

        footer = QHBoxLayout()
        footer.setContentsMargins(12, 0, 12, 0)
        tutorials = QPushButton(tr("tutorials_title"))
        tutorials.clicked.connect(lambda: self.tutorial_requested.emit(""))
        footer.addWidget(tutorials)
        footer.addStretch(1)
        close = QPushButton(tr("help_close"))
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

    def _add_topic_pages(self):
        for topic in TOPICS:
            card = _TopicCard(topic)
            card.show_me_requested.connect(self.show_me_requested.emit)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(card)
            self._stack.addWidget(scroll)
            self._topic_pages[topic.key] = scroll

    def _add_list_items(self):
        entries = [(_TOUR_KEY, tr("help_tour_title"), "tour")]
        entries += [(topic.key, _lang_text(topic.title), topic.icon) for topic in TOPICS]
        entries += [(_SHORTCUTS_KEY, tr("help_shortcuts_title"), "shortcuts")]
        for key, text, icon in entries:
            item = QListWidgetItem(QIcon(_icon_pixmap(icon, _ICON_PX, self)), text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)
            self._list_items[key] = item

    # ── navigation ───────────────────────────────────────────────────────

    def _show_item(self, current, _previous=None):
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key == _TOUR_KEY:
            self._stack.setCurrentWidget(self._tour_card)
        elif key == _SHORTCUTS_KEY:
            self._stack.setCurrentWidget(self._shortcuts_page)
        elif key in self._topic_pages:
            self._stack.setCurrentWidget(self._topic_pages[key])

    def open_topic(self, key):
        item = self._list_items.get(key, self._list_items["first_figure"])
        self._list.setCurrentItem(item)
        self._show_item(item)

    def _visible_keys(self):
        query = self._search.text().strip()
        topics = set(search(query)) if query else {topic.key for topic in TOPICS}
        keys = [_TOUR_KEY] + [topic.key for topic in TOPICS if topic.key in topics]
        if not query or search_shortcuts(query):
            keys.append(_SHORTCUTS_KEY)
        return keys

    def _filter(self, _text=""):
        query = self._search.text().strip()
        if query:
            self._shortcuts_page.set_query(query)
        visible = set(self._visible_keys())
        first = None
        for key, item in self._list_items.items():
            show = key in visible
            item.setHidden(not show)
            if show and first is None:
                first = item
        topic_hits = [key for key in visible if key not in (_TOUR_KEY, _SHORTCUTS_KEY)]
        self._no_results.setVisible(bool(query) and not topic_hits)
        current = self._list.currentItem()
        if (current is None or current.isHidden()) and first is not None:
            self._list.setCurrentItem(first)

    def _open_first_match(self):
        keys = [key for key in self._visible_keys() if key != _TOUR_KEY]
        if keys:
            self.open_topic(keys[0])

    def eventFilter(self, obj, event):
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                row = self._list.currentRow()
                count = self._list.count()
                for _ in range(count):
                    row = (row + step) % count
                    if not self._list.item(row).isHidden():
                        self._list.setCurrentRow(row)
                        break
                return True
        return super().eventFilter(obj, event)


def show_context_help(parent, topic):
    """Open the User Guide on *topic* beside *parent* (used by F1 in dialogs without the main window's wiring)."""
    dlg = HelpDialog(parent, topic=topic)
    parent._context_help = dlg
    dlg.show()
    return dlg
