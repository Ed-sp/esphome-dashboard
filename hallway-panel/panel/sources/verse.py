"""Verse of the day, from YouVersion or from Crossway.

Two providers, because they make opposite trades.

**youversion** is one vendor and one key, and the daily selection is curated
rather than a list somebody typed. Two calls: the verse-of-the-day endpoint
returns a reference and nothing else -- ``{"day": 230, "passage_id": "ROM.6.5"}``
-- and the text comes from ``/bibles/{id}/passages/{ref}``.

Text access is not automatic, which is the thing to know before wiring it up. A
fresh app key reads the daily reference happily, then answers 204 to ``/bibles``
and 403 ``{"message": "Access denied for 206"}`` to every passage -- including
public-domain WEBUS -- because a licence agreement has to be accepted per
version in the developer dashboard first. That is a dashboard step, not a code
one, so this says so in the log and falls back rather than retrying into a wall.
The ESV is not in their catalogue at all (``/bibles/59`` is a 404); Crossway
licenses it separately.

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


def _passage_text(node: Any, depth: int = 0) -> str:
    """Find the scripture in a passage response without betting on one field.

    The success shape is undocumented and could not be observed -- every attempt
    was refused for want of a licence -- so this walks the plausible keys and
    takes the longest string it finds. If YouVersion renames a field the panel
    drops to a psalm rather than raising.
    """
    if isinstance(node, str):
        return node
    if depth > 4:
        return ""
    if isinstance(node, list):
        return " ".join(part for part in (_passage_text(n, depth + 1) for n in node) if part)
    if not isinstance(node, dict):
        return ""

    for field in ("content", "text", "passage", "body", "html"):
        found = node.get(field)
        if isinstance(found, str) and found.strip():
            return found
        if isinstance(found, (dict, list)):
            nested = _passage_text(found, depth + 1)
            if nested:
                return nested

    for field in ("data", "passages", "verses", "result"):
        if field in node:
            nested = _passage_text(node[field], depth + 1)
            if nested:
                return nested
    return ""


def _youversion(day: date, settings: dict[str, Any]) -> Collect | None:
    key = os.environ.get(settings.get("api_key_env", "YOUVERSION_APP_KEY"), "").strip()
    if not key:
        log.info("no YouVersion app key; skipping the verse of the day")
        return None

    # 206 is WEBUS, public domain -- but "public domain" does not mean "no
    # licence to accept". Call /bibles once the agreements are signed to see
    # what this key can actually reach.
    version = str(settings.get("version_id", 206))
    label = str(settings.get("version_label", "") or "")
    day_of_year = day.timetuple().tm_yday

    cache_key = f"yv:{version}:{day_of_year}"
    if (hit := _cached(cache_key)) is not None:
        return hit

    try:
        # 1. The curated reference for this calendar day.
        votd = _yv_get(f"verse_of_the_days/{day_of_year}", key)
        passage_id = str(votd.get("passage_id", "")).strip()
        parsed = _parse_passage_id(passage_id)
        if not parsed:
            return None

        # 2. The text for it. One call -- there is a passages endpoint, it just
        #    needs the licence accepted before it will answer.
        payload = _yv_get(f"bibles/{version}/passages/{passage_id}", key)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 403:
            log.warning(
                "YouVersion refused Bible text for version %s. Accept the licence "
                "agreement for it at developers.youversion.com, then check /bibles "
                "lists it. Falling back to a psalm until then.",
                version,
            )
        else:
            log.info("YouVersion returned %s; falling back", status)
        return _stale(cache_key)
    except (requests.RequestException, ValueError) as exc:
        log.info("YouVersion unreachable (%s); falling back", exc)
        return _stale(cache_key)

    body = _clean(_passage_text(payload))
    if not body:
        log.warning("YouVersion returned no text for %s in version %s", passage_id, version)
        return None

    book, chapter, wanted = parsed
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
