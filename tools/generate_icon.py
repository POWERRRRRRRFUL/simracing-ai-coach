"""Generate src/simcoach/app/style/icons/app.ico.

Renders a minimalist white race car silhouette (side view) on the brand
racing-red (#e63946) rounded square.  The design uses three size-adaptive
tiers so the mark stays readable from 16x16 through 256x256:

  16-24 px  angular wedge + cockpit spike (no wing, no wheels)
  32-48 px  + integrated rear wing, cockpit opening cutout, wheel circles
  64+   px  + smooth Bezier curves, refined nose/cockpit/engine-cover

Requirements: Pillow  (pip install Pillow)
Usage:        python tools/generate_icon.py
"""

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

# Brand colour — must match simcoach.app.style.theme.ACCENT
ACCENT = (230, 57, 70, 255)  # #e63946
WHITE = (255, 255, 255, 255)

TARGET_SIZES = [16, 24, 32, 48, 64, 128, 256]
SUPERSAMPLE = 4  # render at Nx then LANCZOS-downscale
PAD = 0.12  # padding inside the rounded rect

OUTPUT = Path(__file__).resolve().parent.parent / "src/simcoach/app/style/icons/app.ico"


# ── Bezier helper ────────────────────────────────────────────────────────


def _bezier(p0, p1, p2, n=12):
    """Quadratic Bezier from *p0* to *p2* with control point *p1*."""
    return [
        (
            (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1],
        )
        for t in (i / n for i in range(n + 1))
    ]


# ── Size-adaptive car shapes ────────────────────────────────────────────


def _tier_small():
    """16-24 px: angular wedge + rear-biased cockpit spike."""
    body = [
        (0.04, 0.56),
        (0.36, 0.48),
        (0.48, 0.48),
        (0.52, 0.22),
        (0.62, 0.20),
        (0.68, 0.40),
        (0.92, 0.44),
        (0.92, 0.70),
        (0.04, 0.64),
    ]
    return {"polygons": [body], "wheels": [], "cutouts": []}


def _tier_medium():
    """32-48 px: body + integrated rear wing + cockpit opening + wheels."""
    body = [
        (0.02, 0.56),
        (0.24, 0.50),
        (0.40, 0.49),
        (0.50, 0.48),
        (0.54, 0.26),
        (0.62, 0.22),
        (0.68, 0.40),
        (0.76, 0.44),
        (0.80, 0.46),
        # integrated rear wing
        (0.82, 0.46),
        (0.82, 0.17),
        (0.96, 0.17),
        (0.96, 0.23),
        (0.85, 0.23),
        (0.85, 0.48),
        (0.88, 0.48),
        (0.88, 0.70),
        # bottom
        (0.22, 0.70),
        (0.02, 0.62),
    ]
    cockpit_cutout = [
        (0.57, 0.32),
        (0.64, 0.30),
        (0.64, 0.43),
        (0.57, 0.44),
    ]
    return {
        "polygons": [body],
        "wheels": [((0.18, 0.70), 0.055), ((0.72, 0.70), 0.06)],
        "cutouts": [cockpit_cutout],
    }


def _tier_large():
    """64+ px: smooth Bezier outline, cockpit opening, refined details."""
    pts = []

    # Nose: gentle concave curve
    pts += _bezier((0.02, 0.57), (0.22, 0.50), (0.50, 0.49), n=16)[:-1]

    # Pre-cockpit flat
    pts += [(0.50, 0.49)]

    # Cockpit rise: steep entry with slight inward curve
    pts += _bezier((0.50, 0.49), (0.52, 0.30), (0.58, 0.23), n=10)[1:-1]

    # Cockpit peak: gentle arch (airbox / roll hoop)
    pts += _bezier((0.58, 0.23), (0.61, 0.19), (0.64, 0.23), n=8)[:-1]

    # Cockpit drop: steep exit curving into engine cover
    pts += _bezier((0.64, 0.23), (0.66, 0.34), (0.70, 0.40), n=10)[:-1]

    # Engine cover: gentle slope toward rear
    pts += _bezier((0.70, 0.40), (0.74, 0.43), (0.80, 0.46), n=8)[:-1]

    # Rear wing (straight lines — mechanical element)
    pts += [
        (0.82, 0.46),
        (0.82, 0.13),  # pylon left
        (0.97, 0.13),
        (0.97, 0.19),  # wing plate
        (0.85, 0.19),
        (0.85, 0.48),  # pylon right
        (0.88, 0.48),
        (0.88, 0.70),  # body behind pylon + vertical rear face
    ]

    # Bottom: flat underbody + nose underside curve
    pts += [(0.22, 0.70)]
    pts += _bezier((0.22, 0.70), (0.10, 0.68), (0.02, 0.62), n=10)[1:]

    # Cockpit opening (red cutout drawn over the white body)
    cockpit_cutout = [
        (0.55, 0.31),
        (0.65, 0.28),
        (0.66, 0.44),
        (0.55, 0.46),
    ]

    return {
        "polygons": [pts],
        "wheels": [((0.16, 0.70), 0.055), ((0.70, 0.70), 0.06)],
        "cutouts": [cockpit_cutout],
    }


# ── Rendering ────────────────────────────────────────────────────────────


def render_frame(size: int) -> Image.Image:
    """Render one icon frame at *size* px with 4x supersampling."""
    rs = size * SUPERSAMPLE
    img = Image.new("RGBA", (rs, rs), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background rounded rect
    radius = round(rs * 0.20)
    draw.rounded_rectangle([(0, 0), (rs - 1, rs - 1)], radius=radius, fill=ACCENT)

    # Select detail tier
    if size <= 24:
        parts = _tier_small()
    elif size <= 48:
        parts = _tier_medium()
    else:
        parts = _tier_large()

    pad = rs * PAD
    area = rs - 2 * pad

    def to_px(pts):
        return [(pad + x * area, pad + y * area) for x, y in pts]

    # Body polygon(s)
    for poly in parts["polygons"]:
        draw.polygon(to_px(poly), fill=WHITE)

    # Wheel circles
    for (cx, cy), r in parts.get("wheels", []):
        pc = (pad + cx * area, pad + cy * area)
        pr = r * area
        draw.ellipse([pc[0] - pr, pc[1] - pr, pc[0] + pr, pc[1] + pr], fill=WHITE)

    # Cockpit opening cutouts (red over white)
    for cutout in parts.get("cutouts", []):
        draw.polygon(to_px(cutout), fill=ACCENT)

    return img.resize((size, size), Image.LANCZOS)


# ── ICO builder ──────────────────────────────────────────────────────────


def build_ico(frames: dict[int, Image.Image], path: Path) -> None:
    """Write a multi-size ICO file with PNG-compressed frames."""
    sizes = sorted(frames)
    header = struct.pack("<HHH", 0, 1, len(sizes))

    dir_entries = b""
    image_blobs = b""
    data_start = 6 + 16 * len(sizes)

    for s in sizes:
        buf = BytesIO()
        frames[s].save(buf, format="PNG", optimize=True)
        png = buf.getvalue()

        w = s if s < 256 else 0
        h = s if s < 256 else 0
        dir_entries += struct.pack(
            "<BBBBHHII", w, h, 0, 0, 1, 32, len(png), data_start + len(image_blobs)
        )
        image_blobs += png

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + dir_entries + image_blobs)


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    frames = {s: render_frame(s) for s in TARGET_SIZES}
    build_ico(frames, OUTPUT)
    print(f"Generated {OUTPUT}  ({OUTPUT.stat().st_size:,} bytes)")
    for s in TARGET_SIZES:
        print(f"  {s:>3}x{s:<3}")
