"""Aurora alerts from AuroraWatch UK.

Lancaster University run magnetometers in the UK and publish a four-level alert
calibrated to *British* latitudes, which is why this is better than reading a
raw Kp index: Kp 6 means something very different in Shetland than it does in
Oxfordshire, and AuroraWatch has already done that translation.

Their XML API is used rather than the RSS feed. It is versioned, documented, and
returns a machine-readable `status_id` instead of a prose headline to regex.

Two obligations that come with using it, both honoured below:

*   Poll no more often than every three minutes. The default here is fifteen,
    which is well inside the limit and still far fresher than a panel that
    refreshes every twenty.
*   Identify the client with a descriptive User-Agent.

Their documentation also asks that the published thresholds are not adjusted, so
this maps levels to wording without inventing intermediate states. What *is*
configurable is which level is worth interrupting the panel for.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from . import RANKS, Context, SkyEvent, provider

log = logging.getLogger(__name__)

ENDPOINT = "https://aurorawatch-api.lancs.ac.uk/0.2/status/current-status.xml"
USER_AGENT = "hallway-panel/1.0 (personal Home Assistant e-paper display)"
MIN_POLL_SECONDS = 180  # AuroraWatch UK's stated floor; never poll faster

# Ordered so a threshold comparison is just an index lookup.
LEVELS = ["green", "yellow", "amber", "red"]

# Wording per level, and how loudly it should shout. Red outranks every fixed
# event in the almanac: a total lunar eclipse is worth knowing about a week
# ahead, but an aurora visible from Oxfordshire is worth putting your shoes on.
_WORDING: dict[str, tuple[str, str]] = {
    "amber": ("Aurora possible — amber alert, look north", "alert"),
    "red": ("Aurora likely tonight — red alert, visible across the UK", "spectacle"),
}


@dataclass
class Reading:
    level: str
    updated: str | None


_cache: tuple[float, Reading | None] = (0.0, None)


def _parse(xml: str) -> Reading | None:
    """Pull the level out without a DTD-validating parser.

    The document carries an external DTD reference. Resolving it would mean a
    second network request to Lancaster on every poll, and asking an XML parser
    to fetch remote entities is a habit worth not forming, so this reads the two
    attributes it needs directly.
    """
    status = re.search(r'status_id\s*=\s*"([^"]+)"', xml)
    if not status:
        return None
    level = status.group(1).strip().lower()
    if level not in LEVELS:
        log.warning("AuroraWatch returned an unknown status_id %r", level)
        return None

    stamp = re.search(r"<datetime>([^<]+)</datetime>", xml)
    return Reading(level=level, updated=stamp.group(1).strip() if stamp else None)


def current(settings: dict[str, Any] | None = None) -> Reading | None:
    """The current alert level, cached. Returns None if it cannot be fetched."""
    global _cache

    settings = settings or {}
    poll = max(MIN_POLL_SECONDS, int(settings.get("poll_minutes", 15)) * 60)
    fetched_at, cached = _cache
    if cached is not None and (time.monotonic() - fetched_at) < poll:
        return cached

    try:
        response = requests.get(
            settings.get("endpoint", ENDPOINT),
            headers={"User-Agent": settings.get("user_agent", USER_AGENT)},
            # Short: this sits on the render path, and the document is tiny. A
            # slow Lancaster should cost the panel a stale reading, not a
            # timed-out fetch on the device.
            timeout=5,
        )
        response.raise_for_status()
        reading = _parse(response.text)
    except (requests.RequestException, ValueError) as exc:
        log.info("AuroraWatch unreachable (%s); keeping the last reading", exc)
        # Deliberately not clearing the cache. A stale green is harmless, and a
        # stale red for one refresh cycle is better than silently dropping an
        # alert because the wifi hiccuped.
        return cached

    if reading is None:
        return cached

    _cache = (time.monotonic(), reading)
    return reading


@provider("aurora")
def upcoming(context: Context) -> list[SkyEvent]:
    reading = current(context.settings)
    if reading is None:
        return []

    threshold = str(context.settings.get("threshold", "amber")).lower()
    if threshold not in LEVELS:
        log.warning("aurora threshold %r is not one of %s", threshold, LEVELS)
        threshold = "amber"

    if LEVELS.index(reading.level) < LEVELS.index(threshold):
        return []

    text, rank_key = _WORDING.get(reading.level, (f"Aurora {reading.level} alert", "alert"))
    return [SkyEvent(context.today, text, RANKS[rank_key])]
