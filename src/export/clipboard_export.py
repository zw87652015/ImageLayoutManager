"""Copy the rendered figure to the system clipboard as PNG."""
import sys

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, Qt
from PyQt6.QtGui import QImage, QPainter

from src.export.image_exporter import ImageExporter

# Qt's registered Windows clipboard name for PNG. Office, GIMP and LibreOffice
# read it with transparency intact; src/utils/clipboard_paste.py reads the same key.
PNG_WINDOWS_FORMAT = 'application/x-qt-windows-mime;value="PNG"'


def _png_bytes(image: QImage) -> QByteArray:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return data


def _flatten_on_white(image: QImage) -> QImage:
    flat = QImage(image.size(), QImage.Format.Format_RGB32)
    flat.fill(Qt.GlobalColor.white)
    painter = QPainter(flat)
    painter.drawImage(0, 0, image)
    painter.end()
    flat.setDotsPerMeterX(image.dotsPerMeterX())
    flat.setDotsPerMeterY(image.dotsPerMeterY())
    return flat


def build_png_mime(image: QImage, *, platform: str = sys.platform) -> QMimeData:
    """Clipboard payload: alpha-preserving PNG plus an opaque white bitmap.

    The PNG keeps transparency for apps that accept it. The RGB32 bitmap is
    for apps that only read CF_DIB: it has no alpha channel, so Qt's Windows
    converter does not add a second "PNG" format that would collide with ours.
    """
    mime = QMimeData()
    key = PNG_WINDOWS_FORMAT if platform == "win32" else "image/png"
    mime.setData(key, _png_bytes(image))
    mime.setImageData(_flatten_on_white(image))
    return mime


def copy_project_png(project, clipboard) -> QImage:
    """Render *project* at export DPI with transparency and put it on *clipboard*."""
    image = ImageExporter.render_image(project, fmt="PNG", transparent=True)
    clipboard.setMimeData(build_png_mime(image))
    return image
