"""Contact sheet of every icon at the sizes the layout actually uses.

Run: python tools/icon_sheet.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

from panel.render import icons  # noqa: E402
from panel.render.fonts import font  # noqa: E402

SIZES = [14, 18, 26, 30]
COL = 130
ROW = 58
label_font = font("sans", 11)
size_font = font("sans", 9)

names = icons.names()
cols = 5
rows = -(-len(names) // cols)

img = Image.new("1", (cols * COL + 20, rows * ROW + 40), 255)
d = ImageDraw.Draw(img)
d.text((10, 12), "ICON CONTACT SHEET — 14 / 18 / 26 / 30 px", font=label_font, fill=0)

for index, name in enumerate(names):
    cx = 10 + (index % cols) * COL
    cy = 34 + (index // cols) * ROW
    x = cx
    for size in SIZES:
        icons.paste(img, name, x, cy + (30 - size) // 2, size)
        x += size + 5
    d.text((cx, cy + 36), name, font=size_font, fill=0)

out = Path(__file__).resolve().parents[1] / "out" / "icons.png"
out.parent.mkdir(exist_ok=True)
img.save(out)
print(f"wrote {out} ({img.width}x{img.height})")
