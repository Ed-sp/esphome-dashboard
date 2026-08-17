"""Render the hallway panel to a PNG.

    python render_panel.py --sample            # the mockup scene, no HA needed
    python render_panel.py --sample -o out/panel.png
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true", help="render a fixture scene")
    parser.add_argument(
        "--scene",
        default="panel",
        choices=["panel", "quiet"],
        help="which fixture: 'panel' is a busy weekday morning, 'quiet' a dull Sunday",
    )
    parser.add_argument("-o", "--out", default="out/panel.png", type=Path)
    parser.add_argument("--scale", type=int, default=1, help="upscale for on-screen review")
    parser.add_argument(
        "--size",
        type=lambda v: tuple(int(n) for n in v.lower().split("x")),
        default=(800, 480),
        help="panel size, e.g. 640x384 for the 7.5in V1",
    )
    args = parser.parse_args()

    if not args.sample:
        parser.error("live Home Assistant rendering is not wired up yet; pass --sample")

    from panel import sample
    from panel.render import layout

    from panel.render.geometry import for_size
    canvas = layout.render(getattr(sample, args.scene)(), for_size(*args.size))
    image = canvas.image
    if args.scale > 1:
        from PIL import Image

        image = image.resize(
            (image.width * args.scale, image.height * args.scale), Image.NEAREST
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out, optimize=True, bits=1)
    print(f"wrote {args.out} ({image.width}x{image.height}, {args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
