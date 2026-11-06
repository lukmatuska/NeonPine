#!/usr/bin/env python3
"""Renders the app icon (drawn in widgets.py) to PNG and a multi-size ICO: make_icons.py OUTDIR"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from neonpine_companion.widgets import app_icon_pixmap  # noqa: E402


def png_bytes(pm):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(buf.data())


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    _app = QApplication(sys.argv)
    app_icon_pixmap(256).save(os.path.join(out, "neonpine-companion.png"))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [png_bytes(app_icon_pixmap(s)) for s in sizes]
    # ICO with PNG entries (Windows Vista and later)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, data = b"", b""
    for s, img in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset + len(data))
        data += img
    with open(os.path.join(out, "neonpine-companion.ico"), "wb") as f:
        f.write(head + entries + data)
    print("icons in", os.path.abspath(out))


if __name__ == "__main__":
    main()
