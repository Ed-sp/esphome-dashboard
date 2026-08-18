"""Verse of the day, from YouVersion or from Crossway.

Two providers, because they make opposite trades.

**youversion** is one vendor and one key, and the daily selection is curated
rather than a list somebody typed. It costs two calls: their verse-of-the-day
endpoint returns a reference and nothing else -- ``{"day": 1, "passage_id":
"JHN.3.16"}`` -- and there is no endpoint that turns a passage_id into text, so
the second call pulls the whole chapter and this filters it. The ESV is not
among the versions their platform API documents; Crossway licenses it
separately.

**esv** is one call against a documented response, and it is the ESV. The daily
selection comes from data/verses.yaml instead, which is a list somebody typed --
but references carry no copyright, so it lives in the repo and is yours to edit.

Either way the text is fetched, never stored. That keeps the licensing simple
and means the panel shows the publisher's current text rather than whatever was
pasted into a file once.
"""

from __future__ import annotations

import logging
import os
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

ESV_ENDPOINT = "https://api.esv.org/v3/passage/text/"
YV_BASE = "https://api.youversion.com/v1"

# One passage per day, so at most one fetch per day per provider. Keyed by what
# was asked for, so the same passage after a restart is a cache hit.
_cache: dict[str, tuple[float, Collect]] = {}
_CACHE_SECONDS = 12 * 3600

# On the render path, so short. A slow publisher costs the panel a psalm, not a
# timed-out fetch on the device.
_TIMEOUT = 6

_BOOKS = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
    "DEU": "Deuteronomy", "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth",
    "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
    "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra", "NEH": "Nehemiah",
    "EST": "Esther", "JOB": "Job", "PSA": "Psalm", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SNG": "Song of Solomon", "ISA": "Isaiah",
    "JER": "Jeremiah", "LAM": "Lamentations", "EZK": "Ezekiel", "DAN": "Daniel",
    "HOS": "Hosea", "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah",
    "JON": "Jonah", "MIC": "Micah", "NAM": "Nahum", "HAB": "Habakkuk",
    "ZEP": "Zephaniah", "HAG": "Haggai", "ZEC": "Zechariah", "MAL": "Malachi",
    "MAT": "Matthew", "MRK": "Mark", "LUK": "Luke", "JHN": "John",
    "ACT": "Acts", "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians",
    "GAL": "Galatians", "EPH": "Ephesians", "PHP": "Philippians",
    "COL": "Colossians", "1TH": "1 Thessalonians", "2TH": "2 Thessalonians",
    "1TI": "1 Timothy", "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon",
    "HEB": "Hebrews", "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter",
    "1JN": "1 John", "2JN": "2 John", "3JN": "3 John", "JUD": "Jude",
    "REV": "Revelation",
}


@lru_cache(maxsize=1)
def references() -> list[str]:
    import yaml

    if not DATA.is_file():
        log.warning("%s is missing; the esv provider has nothing to look up", DATA)
        return []
    with DATA.open("r", encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("passages") or []


def _clean(text: str) -> str:
    """Strip layout artefacts down to prose.

    Both APIs return text wrapped for something other than this panel: hard
    newlines mid-sentence, leading indents, paragraph breaks as blank lines, and
    sometimes bracketed verse numbers. The panel wraps its own text.
    """
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip().strip("“”").strip()


def _cached(key: str) -> Collect | None:
    hit = _cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _CACHE_SECONDS:
        return hit[1]
    return None


def _stale(key: str) -> Collect | None:
    """The last good answer regardless of age -- better than a psalm mid-outage."""
    hit = _cache.get(key)
    return hit[1] if hit else None


def _store(key: str, collect: Collect) -> Collect:
    _cache[key] = (time.monotonic(), collect)
    return collect


# --------------------------------------------------------------------- esv


def _esv(day: date, settings: dict[str, Any]) -> Collect | None:
    key = os.environ.get(settings.get("api_key_env", "ESV_API_KEY"), "").strip()
    if not key:
        log.info("no ESV API key; skipping the verse of the day")
        return None

    passages = references()
    if not passages:
        return None
    reference = passages[day.toordinal() % len(passages)]

    cache_key = f"esv:{reference}"
    if (hit := _cached(cache_key)) is not None:
        return hit

    try:
        response = requests.get(
            ESV_ENDPOINT,
            params={
                "q": reference,
                # Everything off: the panel wants prose, not an apparatus.
                "include-headings": "false",
                "include-footnotes": "false",
                "include-verse-numbers": "false",
                "include-passage-references": "false",
                # Attribution goes in the block title, where it reads as a
                # citation rather than "(ESV)" stuck mid-sentence.
                "include-short-copyright": "false",
                "include-passage-horizontal-lines": "false",
                "include-heading-horizontal-lines": "false",
            },
            headers={"Authorization": f"Token {key}"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.info("ESV API unreachable (%s); falling back", exc)
        return _stale(cache_key)

    body = _clean(" ".join(payload.get("passages") or []))
    if not body:
        log.warning("ESV API returned nothing for %r", reference)
        return None

    title = payload.get("canonical") or reference
    return _store(cache_key, Collect(title=f"{title} · ESV", text=body))


# -------------------------------------------------------------- youversion


def _parse_passage_id(passage_id: str) -> tuple[str, int, list[int]] | None:
    """``JHN.3.16`` or ``JHN.3.16-17`` -> ("JHN", 3, [16, 17])."""
    match = re.match(
        r"^([A-Z0-9]{3})\.(\d+)\.(\d+)(?:\s*-\s*(?:[A-Z0-9]{3}\.\d+\.)?(\d+))?$",
        passage_id.strip().upper(),
    )
    if not match:
        log.warning("could not parse a passage id from %r", passage_id)
        return None
    book, chapter, first, last = match.groups()
    start, end = int(first), int(last or first)
    if end < start or end - start > 12:
        end = start
    return book, int(chapter), list(range(start, end + 1))


def _yv_get(path: str, key: str, params: dict | None = None) -> Any:
    response = requests.get(
        f"{YV_BASE}/{path.lstrip('/')}",
        headers={"X-YVP-App-Key": key},
        params=params or {},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _verse_text(node: Any) -> str:
    """Pull text out of a verse record without betting on one field name.

    The platform API's verse shape is not in the quick reference, so this walks
    the plausible keys rather than asserting one. If YouVersion renames a field
    the panel drops to a psalm instead of raising.
    """
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    for field in ("content", "text", "value", "body"):
        found = node.get(field)
        if isinstance(found, str) and found.strip():
            return found
    return ""


def _verse_number(node: Any) -> int | None:
    if not isinstance(node, dict):
        return None
    for field in ("verse", "number", "verse_number", "usfm", "reference"):
        found = node.get(field)
        if isinstance(found, int):
            return found
        if isinstance(found, str):
            digits = re.findall(r"\d+", found)
            if digits:
                return int(digits[-1])
    return None


def _youversion(day: date, settings: dict[str, Any]) -> Collect | None:
    key = os.environ.get(settings.get("api_key_env", "YOUVERSION_APP_KEY"), "").strip()
    if not key:
        log.info("no YouVersion app key; skipping the verse of the day")
        return None

    # 206 is WEBUS, public domain, so it is always licensable. Change it in
    # panel.yaml once /bibles tells you what your key can actually reach.
    version = str(settings.get("version_id", 206))
    label = str(settings.get("version_label", "") or "")
    day_of_year = day.timetuple().tm_yday

    cache_key = f"yv:{version}:{day_of_year}"
    if (hit := _cached(cache_key)) is not None:
        return hit

    try:
        # 1. The curated reference for this calendar day.
        votd = _yv_get(f"verse_of_the_days/{day_of_year}", key)
        parsed = _parse_passage_id(str(votd.get("passage_id", "")))
        if not parsed:
            return None
        book, chapter, wanted = parsed

        # 2. The chapter, filtered. There is no endpoint turning a passage_id
        #    into text, which is what makes this two calls rather than one.
        payload = _yv_get(f"bibles/{version}/books/{book}/chapters/{chapter}/verses", key)
    except (requests.RequestException, ValueError) as exc:
        log.info("YouVersion unreachable (%s); falling back", exc)
        return _stale(cache_key)

    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        log.warning("YouVersion returned an unexpected chapter shape for %s %s", book, chapter)
        return None

    picked = [_verse_text(row) for row in rows if _verse_number(row) in wanted]
    body = _clean(" ".join(text for text in picked if text))
    if not body:
        log.warning("no verse text found for %s.%s.%s", book, chapter, wanted)
        return None

    name = _BOOKS.get(book, book.title())
    span = f"{wanted[0]}-{wanted[-1]}" if len(wanted) > 1 else str(wanted[0])
    title = f"{name} {chapter}:{span}"
    return _store(cache_key, Collect(title=f"{title} · {label}" if label else title, text=body))


# -------------------------------------------------------------------- entry

_PROVIDERS = {"esv": _esv, "youversion": _youversion}


def for_date(day: date, settings: dict[str, Any] | None = None) -> Collect | None:
    """Today's passage, or None if switched off, unconfigured or unreachable."""
    settings = settings or {}
    if not settings.get("enabled", False):
        return None

    name = str(settings.get("provider", "esv")).lower()
    provider = _PROVIDERS.get(name)
    if provider is None:
        log.warning("unknown verse provider %r; expected one of %s", name, sorted(_PROVIDERS))
        return None

    try:
        return provider(day, settings)
    except Exception as exc:  # noqa: BLE001 - a verse must never sink the render
        log.warning("verse provider %r failed: %s", name, exc)
        return None
