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

log = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[2] / "data" / "offline.yaml"

W, H = 800, 480
M = 24


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
) -> Canvas:
    now = now or datetime.now()
    c = Canvas(W, H)

    when = (
        f"LAST GOOD DATA {last_good:%H:%M}" if last_good else "NO GOOD DATA YET"
    )
    c.text(M, 36, f"CAN'T REACH HOME  ·  {when}", Text("sans_bold", 12, tracking=1.6))
    c.rule(M, 52, W - M, 52, weight=2)

    # A dithered crescent: the same shading vocabulary as the graph, so the
    # fallback still looks like it belongs to the panel rather than an error
    # dialogue that wandered in.
    halo, moon = 92, 132
    c.dither_fill(2, clip=_disc(400, 186, halo))
    icons.paste(c.image, "moon", 400 - moon / 2, 186 - moon / 2, moon)
    for x, y, size in ((272, 92, 20), (528, 246, 15), (306, 272, 12)):
        icons.paste(c.image, "spark", x, y, size)

    joke = _joke(now)
    if joke:
        c.text(W / 2, 336, joke["setup"], Text("serif", 21), anchor="center")
        c.text(W / 2, 370, joke["punchline"], Text("serif", 21), anchor="center")

    if reason:
        c.text(
            W / 2,
            H - 30,
            c.ellipsize(reason, Text("sans", 10), W - 2 * M),
            Text("sans", 10),
            anchor="center",
        )

    return c


def _disc(cx: float, cy: float, r: float, steps: int = 72) -> list[tuple[float, float]]:
    import math

    return [
        (cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ]
