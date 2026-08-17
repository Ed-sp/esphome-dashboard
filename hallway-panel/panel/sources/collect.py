"""The collect for the day, with a psalm or Pauline prayer covering the gaps.

The table is keyed by `panel.liturgy`, which resolves any date back to the
Sunday or principal feast governing it. Where the table has no entry the panel
falls back to a short passage of scripture, chosen deterministically from the
date so it is stable through the day and rotates across days rather than landing
on the same verse every Tuesday.

Nothing here is generated. If a key is missing it falls back rather than
inventing a collect, because the text ends up on a wall.
"""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .. import liturgy
from ..model import Collect

log = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[2] / "data"


def _read(name: str) -> Any:
    path = DATA / name
    if not path.is_file():
        log.warning("%s is missing; the collect block will stay empty", path)
        return None
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=1)
def load_collects() -> dict[str, dict[str, str]]:
    raw = _read("collects.yaml") or {}
    return raw.get("collects") or {}


@lru_cache(maxsize=1)
def load_fallbacks() -> list[dict[str, str]]:
    raw = _read("fallbacks.yaml") or {}
    return raw.get("passages") or []


def for_date(day: date | None = None) -> Collect | None:
    day = day or date.today()
    key = liturgy.key_for(day)

    entry = load_collects().get(key)
    if entry and entry.get("text"):
        return Collect(title=f"Collect · {liturgy.title_for(key)}", text=entry["text"].strip())

    passages = load_fallbacks()
    if not passages:
        return None

    passage = passages[day.toordinal() % len(passages)]
    return Collect(
        title=passage.get("reference", "Scripture"),
        text=(passage.get("text") or "").strip(),
    )


def coverage() -> tuple[int, int]:
    """(keys with a collect, keys the calendar produces this year)."""
    table = load_collects()
    keys = [key for _, key in liturgy.keys_in_year(date.today().year)]
    return sum(1 for key in keys if key in table), len(keys)
