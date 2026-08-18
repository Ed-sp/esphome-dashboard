"""Verse of the day, in the ESV, from Crossway's API.

Splitting reference from text is the whole design. `data/verses.yaml` holds
references, which are facts and carry no copyright, so they live in the repo.
The ESV text is licensed, so it is fetched at render time with your own key and
never committed -- which also means the panel shows Crossway's current text
rather than whatever was pasted into a file once.

YouVersion was the obvious first stop and is not worth it here. Its
verse-of-the-day endpoint returns `{"day": 1, "passage_id": "JHN.3.16"}` -- a
reference and nothing else -- and it needs its own app key on top of the ESV
one. Two keys to end up exactly where a local list of references gets you.

Where this sits in the block: the collect wins when the day has one, this comes
next, and the psalm fallback catches the rest. So on the ~48 days a year with no
collect the panel shows a fresh ESV passage instead of cycling eighteen psalms.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from ..model import Collect

log = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[2] / "data" / "verses.yaml"
ENDPOINT = "https://api.esv.org/v3/passage/text/"

# One reference per day, so at most one fetch per day. Keyed by reference rather
# than by date: the same passage on the same day after a restart is a cache hit.
_cache: dict[str, tuple[float, Collect]] = {}
_CACHE_SECONDS = 12 * 3600


@lru_cache(maxsize=1)
def references() -> list[str]:
    import yaml

    if not DATA.is_file():
        log.warning("%s is missing; the verse of the day will not appear", DATA)
        return []
    with DATA.open("r", encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("passages") or []


def _clean(text: str) -> str:
    """Strip the API's layout artefacts down to prose.

    Even with headings, footnotes and verse numbers turned off, the response
    arrives wrapped for a monospace terminal: hard newlines mid-sentence, a
    leading indent, and paragraph breaks as blank lines. The panel wraps its own
    text, so all of that has to go.
    """
    text = re.sub(r"\[\d+\]", "", text)  # stray verse numbers, if any survive
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip().strip("“”").strip()


def for_date(day: date, settings: dict[str, Any] | None = None) -> Collect | None:
    """Today's passage, or None if it is switched off or unreachable."""
    settings = settings or {}
    if not settings.get("enabled", False):
        return None

    import os

    key = os.environ.get(settings.get("api_key_env", "ESV_API_KEY"), "").strip()
    if not key:
        log.info("no ESV API key; skipping the verse of the day")
        return None

    passages = references()
    if not passages:
        return None
    reference = passages[day.toordinal() % len(passages)]

    cached = _cache.get(reference)
    if cached and (time.monotonic() - cached[0]) < _CACHE_SECONDS:
        return cached[1]

    try:
        response = requests.get(
            ENDPOINT,
            params={
                "q": reference,
                # Everything off: the panel wants prose, not an apparatus.
                "include-headings": "false",
                "include-footnotes": "false",
                "include-verse-numbers": "false",
                "include-passage-references": "false",
                # Attribution goes in the block's title instead, where it reads
                # as a citation rather than "(ESV)" stuck mid-sentence.
                "include-short-copyright": "false",
                "include-passage-horizontal-lines": "false",
                "include-heading-horizontal-lines": "false",
            },
            headers={"Authorization": f"Token {key}"},
            # On the render path, so short. A slow Crossway costs the panel a
            # psalm, not a timed-out fetch on the device.
            timeout=6,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.info("ESV API unreachable (%s); falling back", exc)
        return cached[1] if cached else None

    body = " ".join(payload.get("passages") or []).strip()
    if not body:
        log.warning("ESV API returned nothing for %r", reference)
        return None

    collect = Collect(
        title=f"{payload.get('canonical') or reference} · ESV",
        text=_clean(body),
    )
    _cache[reference] = (time.monotonic(), collect)
    return collect
