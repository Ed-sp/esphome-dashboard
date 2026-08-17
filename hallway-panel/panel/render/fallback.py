"""The screen shown when there is nothing trustworthy to draw.

Three failure states, three behaviours, and only the last one lands here:

*   The render succeeded but nothing changed -- the device gets a 304 and does
    not refresh at all.
*   Home Assistant is unreachable but the last good image is recent -- keep
    showing it. A forecast an hour old is still roughly right, and a panel that
    blanks at the first dropped packet would be worse than one slightly stale.
*   Home Assistant has been unreachable long enough that the last image should
    not be trusted -- this.

The important part is that it looks *deliberate*. A blank panel or, worse, the
fixture scene reads as real data, and someone would leave the house dressed for
the wrong weather. This says plainly that it does not know, gives the time it
last did, and puts a joke where the forecast usually is.
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

from . import icons
from .canvas import Canvas, Text
from .geometry import Geometry, V2

log = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[2] / "data" / "offline.yaml"


@lru_cache(maxsize=1)
def _jokes() -> list[dict[str, str]]:
    if not DATA.is_file():
        log.warning("%s is missing; the fallback screen will be wordless", DATA)
        return []
    with DATA.open("r", encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("jokes") or []


def _joke(seed: datetime) -> dict[str, str] | None:
    jokes = _jokes()
    if not jokes:
        return None
    # By the hour rather than at random: it stays put across the retries within
    # an outage instead of reshuffling every twenty minutes, but a long outage
    # does not stare back with the same line for a day.
    return jokes[(seed.toordinal() * 24 + seed.hour) % len(jokes)]


def render(
    *,
    reason: str | None = None,
    last_good: datetime | None = None,
    now: datetime | None = None,
    geometry: Geometry | None = None,
) -> Canvas:
    now = now or datetime.now()
    g = geometry or V2
    w, h = g.width, g.height
    m = g.margin * 2
    c = Canvas(w, h)

    # Placed proportionally rather than from a tuned table: this screen is one
    # heading, one drawing and two lines, so it survives being laid out by
    # fractions in a way the dashboard would not.
    small = w < 700
    when = f"LAST GOOD DATA {last_good:%H:%M}" if last_good else "NO GOOD DATA YET"
    c.text(m, h * 0.075, f"CAN'T REACH HOME  ·  {when}",
           Text("sans_bold", 11 if small else 12, tracking=1.4))
    c.rule(m, h * 0.108, w - m, h * 0.108, weight=2)

    # A dithered crescent, in the same shading vocabulary as the graph, so the
    # fallback still looks like it belongs to the panel rather than an error
    # dialogue that wandered in.
    cx, cy = w / 2, h * 0.39
    halo = h * 0.19
    moon = halo * 1.44
    c.dither_fill(2, clip=_disc(cx, cy, halo))
    icons.paste(c.image, "moon", cx - moon / 2, cy - moon / 2, round(moon))
    for dx, dy, size in ((-0.16, -0.20, 20), (0.16, 0.125, 15), (-0.12, 0.18, 12)):
        icons.paste(c.image, "spark", cx + dx * w, cy + dy * h, round(size * (0.8 if small else 1)))

    joke = _joke(now)
    if joke:
        style = Text("serif", 17 if small else 21)
        leading = h * 0.072
        for i, line in enumerate((joke["setup"], joke["punchline"])):
            c.text(cx, h * 0.70 + i * leading, c.ellipsize(line, style, w - m * 2),
                   style, anchor="center")

    if reason:
        style = Text("sans", 9 if small else 10)
        c.text(cx, h - m * 0.6, c.ellipsize(reason, style, w - m * 2), style, anchor="center")

    return c


def _disc(cx: float, cy: float, r: float, steps: int = 72) -> list[tuple[float, float]]:
    import math

    return [
        (cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ]
