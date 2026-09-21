from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QFont, QTextCursor, QTextFormat
from PyQt6.QtWidgets import QGraphicsTextItem, QStyleOptionGraphicsItem

PT_TO_MM = 25.4 / 72.0
REFERENCE_PX = 96


def uses_points(project):
    return getattr(project, 'typography_mode', 'legacy') == 'points'


def reference_font(family, weight='normal'):
    font = QFont(family)
    font.setPixelSize(REFERENCE_PX)
    font.setBold(weight == 'bold')
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def text_scale_mm(size_pt):
    return float(size_pt) * PT_TO_MM / REFERENCE_PX


def configure_point_text(item, family, size_pt, weight, color):
    item.setFont(reference_font(family, weight))
    item.setDefaultTextColor(QColor(color))
    document = item.document()
    document.setDocumentMargin(0.0)
    ranges = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                ranges.append((fragment.position(), fragment.length(), fragment.charFormat()))
            iterator += 1
        block = block.next()
    for position, length, fmt in ranges:
        fmt.clearProperty(QTextFormat.Property.FontPointSize)
        fmt.setProperty(QTextFormat.Property.FontPixelSize, REFERENCE_PX)
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)
    item.setScale(text_scale_mm(size_pt))


def point_text_item(text, family, size_pt, weight, color, rich=True):
    item = QGraphicsTextItem()
    if rich:
        item.setHtml(text)
    else:
        item.setPlainText(text)
    configure_point_text(item, family, size_pt, weight, color)
    return item


def draw_point_text(painter, item, x, y, device_scale=1.0):
    painter.save()
    painter.translate(x, y)
    painter.scale(item.scale() * device_scale, item.scale() * device_scale)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.restore()
