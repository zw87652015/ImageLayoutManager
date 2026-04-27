"""
Generate assets/icon_figpack.icns from assets/icon_figpack.svg using
PyQt6 (QSvgRenderer) for rasterisation and Pillow for .icns packing.

Usage:
    python build_icns_figpack.py
"""

import io
import struct
import sys
import os

# ---------------------------------------------------------------------------
# Rasterise SVG → PNG bytes at each required size via PyQt6
# ---------------------------------------------------------------------------

SIZES = [16, 32, 64, 128, 256, 512, 1024]

SVG_PATH  = os.path.join(os.path.dirname(__file__), "assets", "icon_figpack.svg")
ICNS_PATH = os.path.join(os.path.dirname(__file__), "assets", "icon_figpack.icns")


def svg_to_png_bytes(svg_path: str, size: int) -> bytes:
    from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QSize
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    renderer = QSvgRenderer(svg_path)
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()

    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


# ---------------------------------------------------------------------------
# Pack PNGs into .icns
# icns format: 4-byte magic, 4-byte total length, then chunks:
#   chunk = 4-byte OSType + 4-byte chunk-length (including 8-byte header) + data
# ---------------------------------------------------------------------------

# Mapping: pixel size → icns OSType
OSTYPE = {
    16:   b"icp4",   # 16×16
    32:   b"icp5",   # 32×32
    64:   b"icp6",   # 64×64
    128:  b"ic07",   # 128×128
    256:  b"ic08",   # 256×256
    512:  b"ic09",   # 512×512
    1024: b"ic10",   # 1024×1024
}

ICNS_MAGIC = b"icns"


def build_icns(png_map: dict) -> bytes:
    """png_map: {size_int: png_bytes}"""
    chunks = b""
    for size, data in sorted(png_map.items()):
        ostype = OSTYPE[size]
        chunk_len = 8 + len(data)
        chunks += ostype + struct.pack(">I", chunk_len) + data
    total = 8 + len(chunks)
    return ICNS_MAGIC + struct.pack(">I", total) + chunks


def main():
    print(f"Reading SVG: {SVG_PATH}")
    png_map = {}
    for size in SIZES:
        print(f"  Rendering {size}×{size} …", end=" ", flush=True)
        png_map[size] = svg_to_png_bytes(SVG_PATH, size)
        print(f"{len(png_map[size])} bytes")

    icns_data = build_icns(png_map)
    with open(ICNS_PATH, "wb") as f:
        f.write(icns_data)
    print(f"\nWrote {len(icns_data)} bytes → {ICNS_PATH}")


if __name__ == "__main__":
    main()
