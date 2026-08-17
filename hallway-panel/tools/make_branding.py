"""Generate the add-on's icon.png and logo.png.

The Supervisor shows these in the add-on store. Drawn rather than sourced, in
the panel's own 1-bit vocabulary -- a framed dashboard with the dithered
temperature trace -- so the store entry looks like the thing it installs.

    python tools/make_branding.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

from panel.render.fonts import font  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

INK = (21, 24, 27)
PAPER = (255, 255, 255)
MOUNT = (232, 232, 226)


def _trace(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], weight: int) -> None:
    """A temperature curve with dithered shading beneath, scaled into `box`."""
    x0, y0, x1, y1 = box
    points = [0.55, 0.72, 0.88, 1.0, 0.92, 0.7, 0.5, 0.36, 0.3, 0.42, 0.62]
    step = (x1 - x0) / (len(points) - 1)
    xy = [(x0 + i * step, y1 - v * (y1 - y0)) for i, v in enumerate(points)]

    # Dither the area under the curve, coarser than the panel's own so it still
    # reads at 128px.
    for i in range(len(xy) - 1):
        for px in range(int(xy[i][0]), int(xy[i + 1][0]) + 1):
            t = (px - xy[i][0]) / max(step, 1)
            top = xy[i][1] + (xy[i + 1][1] - xy[i][1]) * t
            for py in range(int(top), int(y1)):
                if (px + py) % 3 == 0 and (px * py) % 2 == 0:
                    draw.point((px, py), fill=INK)

    draw.line(xy, fill=INK, width=weight, joint="curve")
    draw.line([(x0, y1), (x1, y1)], fill=INK, width=max(1, weight // 2))


def icon(size: int = 128) -> Image.Image:
    img = Image.new("RGB", (size, size), MOUNT)
    d = ImageDraw.Draw(img)

    pad = size // 10
    d.rectangle([pad, pad, size - pad, size - pad], fill=PAPER, outline=INK, width=3)

    inner = pad + 10
    d.line([(inner, inner + 8), (size - inner, inner + 8)], fill=INK, width=3)
    _trace(d, (inner, inner + 18, size - inner, size - inner - 14), weight=3)
    d.line(
        [(inner, size - inner - 6), (size - inner, size - inner - 6)], fill=INK, width=2
    )
    return img


def logo(width: int = 320, height: int = 128) -> Image.Image:
    img = Image.new("RGB", (width, height), PAPER)
    d = ImageDraw.Draw(img)

    panel_w = 132
    d.rectangle([14, 20, 14 + panel_w, height - 20], fill=PAPER, outline=INK, width=3)
    d.line([(26, 40), (14 + panel_w - 12, 40)], fill=INK, width=2)
    _trace(d, (26, 48, 14 + panel_w - 12, height - 40), weight=3)
    d.line([(26, height - 34), (14 + panel_w - 12, height - 34)], fill=INK, width=2)

    d.text((176, 44), "HALLWAY", font=font("sans_bold", 26), fill=INK)
    d.text((176, 74), "PANEL", font=font("sans_bold", 26), fill=INK)
    return img


def main() -> int:
    icon(128).save(ROOT / "icon.png")
    logo(320, 128).save(ROOT / "logo.png")
    for name in ("icon.png", "logo.png"):
        path = ROOT / name
        print(f"wrote {path.relative_to(ROOT.parent)} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
