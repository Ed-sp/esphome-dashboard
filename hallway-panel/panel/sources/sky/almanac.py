"""Eclipses and meteor showers, from the static table in data/sky.yaml.

Static rather than fetched, deliberately. Shower peaks land within a day of the
same date every year and eclipse dates are known centuries ahead, so an API
would add a network dependency and a failure mode in exchange for nothing.

Registered as two separate providers so either can be switched off on its own --
the showers are the ones most likely to wear out their welcome.
"""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import RANKS, Context, SkyEvent, provider

log = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[3] / "data" / "sky.yaml"


@lru_cache(maxsize=1)
def tables() -> dict[str, Any]:
    if not DATA.is_file():
        log.warning("%s is missing; eclipses and showers will not appear", DATA)
        return {}
    with DATA.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@provider("showers")
def showers(context: Context) -> list[SkyEvent]:
    out: list[SkyEvent] = []
    minimum = context.settings.get("min_zhr", 0)

    for entry in tables().get("showers") or []:
        if entry.get("zhr", 0) < minimum:
            continue
        month, day = (int(part) for part in str(entry["peak"]).split("-"))

        # Both years, so a peak in early January is still found in late December.
        for year in {context.today.year, context.horizon.year}:
            try:
                peak = date(year, month, day)
            except ValueError:
                continue
            if not context.within(peak):
                continue

            text = f"{entry['name']} peak {context.when_word(peak, night=True)}"
            if entry.get("note"):
                text = f"{text}, {entry['note']}"
            default = RANKS["shower_major"] if entry.get("zhr", 0) >= 50 else RANKS["shower_minor"]
            out.append(SkyEvent(peak, text, entry.get("rank", default)))
    return out


@provider("eclipses")
def eclipses(context: Context) -> list[SkyEvent]:
    out: list[SkyEvent] = []
    for entry in tables().get("eclipses") or []:
        when = entry["date"]
        if isinstance(when, str):
            when = date.fromisoformat(when)
        if not context.within(when):
            continue

        parts = [f"{entry['kind']} {context.when_word(when)}"]
        if entry.get("time"):
            parts.append(entry["time"])
        if entry.get("note"):
            parts.append(entry["note"])

        default = (
            RANKS["eclipse_total"]
            if "total" in str(entry["kind"]).lower()
            else RANKS["eclipse_partial"]
        )
        out.append(SkyEvent(when, ", ".join(parts), entry.get("rank", default)))
    return out
