#!/usr/bin/env python3
"""One-time utility: generate src/simcoach/app/style/icons/app.ico.

Usage:
    python scripts/create_icon.py

Requires PySide6 (already a GUI dependency).
After running, commit the generated app.ico to git.
To redesign the icon, edit BG_COLOR / TEXT_COLOR / the drawing code,
re-run this script, then commit the updated app.ico.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

# ── Icon design ─────────────────────────────────────────────────────────────
BG_COLOR   = "#e63946"   # Racing-red — matches the GUI / HTML report accent
TEXT_COLOR = "#ffffff"   # White "SC" lettermark


def _render_size(size: int) -> bytes:
    """Render one icon frame; return raw BGRA pixel rows (bottom-up, ICO order)."""
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Rounded-rect background
    pad    = max(1, size // 8)
    radius = max(2, size // 5)
    rect   = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    painter.setBrush(QColor(BG_COLOR))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(rect, radius, radius)

    # "SC" lettermark — only at ≥ 32 px (unreadable at 16 px)
    if size >= 32:
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(max(8, size * 40 // 100))
        painter.setFont(font)
        painter.setPen(QColor(TEXT_COLOR))
        painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "SC")

    painter.end()

    # Extract BGRA rows bottom-up (ICO stores rows from bottom to top)
    rows: list[bytes] = []
    for y in range(size - 1, -1, -1):
        row = bytearray(size * 4)
        for x in range(size):
            argb     = img.pixel(x, y)   # 0xAARRGGBB
            a        = (argb >> 24) & 0xFF
            r        = (argb >> 16) & 0xFF
            g        = (argb >>  8) & 0xFF
            b        =  argb        & 0xFF
            base     = x * 4
            row[base    ] = b
            row[base + 1] = g
            row[base + 2] = r
            row[base + 3] = a
        rows.append(bytes(row))
    return b"".join(rows)


def _bitmapinfoheader(w: int, h: int) -> bytes:
    """40-byte BITMAPINFOHEADER for a 32-bit ARGB ICO frame (no AND mask)."""
    return struct.pack(
        "<IiiHHIIiiII",
        40,          # biSize
        w,           # biWidth
        h,           # biHeight (positive = bottom-up rows; no AND mask for 32-bit)
        1,           # biPlanes
        32,          # biBitCount
        0,           # biCompression (BI_RGB)
        w * h * 4,   # biSizeImage
        0, 0,        # biXPelsPerMeter, biYPelsPerMeter
        0, 0,        # biClrUsed, biClrImportant
    )


def build_ico(sizes: list[int]) -> bytes:
    """Build and return a Windows ICO binary containing one frame per size."""
    n            = len(sizes)
    header_bytes = 6 + n * 16   # ICONDIR (6) + n × ICONDIRENTRY (16 each)

    frames: list[tuple[int, bytes]] = []
    for size in sizes:
        pixels = _render_size(size)
        data   = _bitmapinfoheader(size, size) + pixels
        frames.append((size, data))

    # ICONDIR — magic=0, type=1 (ICO), count=n
    ico = struct.pack("<HHH", 0, 1, n)

    # ICONDIRENTRY for each frame  (256 stored as 0 per the ICO spec)
    offset = header_bytes
    for size, data in frames:
        w_byte = size if size < 256 else 0
        h_byte = size if size < 256 else 0
        ico += struct.pack(
            "<BBBBHHII",
            w_byte, h_byte,   # width, height (0 means 256)
            0, 0,             # colorCount, reserved
            1, 32,            # planes, bitCount
            len(data),        # dataSize
            offset,           # dataOffset from start of file
        )
        offset += len(data)

    # Image data blocks
    for _, data in frames:
        ico += data

    return ico


def main() -> None:
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication(sys.argv)   # required for QPainter

    out = (
        Path(__file__).resolve().parent.parent
        / "src" / "simcoach" / "app" / "style" / "icons" / "app.ico"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    print("Rendering icon at 16, 32, 48, 256 px …")
    ico_data = build_ico([16, 32, 48, 256])
    out.write_bytes(ico_data)
    print(f"Done — {len(ico_data):,} bytes written to:\n  {out}")
    print("Commit this file to git to make the icon permanent.")


if __name__ == "__main__":
    main()
