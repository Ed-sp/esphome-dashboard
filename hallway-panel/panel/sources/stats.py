"""The numbers in the bottom-right block.

`pair` and `spotify_hours` are the two-per-person kinds -- one number per
`config.people` entry (Steps off a sensor each, Music off each person's own
Spotify history), rendered as a column under each person's badge rather than a
single value. `history_hours` and `sum_energy` stay single aggregate numbers.

A slot with no data renders an em dash rather than disappearing, so the block
keeps its shape and the panel does not reflow week to week.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import Config
from ..hass import Hass, State, window_start
from ..model import Stat
from . import spotify

log = logging.getLogger(__name__)

NO_DATA = "—"


def _hours_minutes(seconds: float) -> str:
    total = round(seconds / 60)
    return f"{total // 60}h {total % 60:02d}m"


def _compact(value: float) -> str:
    if value >= 10_000:
        return f"{value / 1000:.0f}k"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return f"{round(value)}"


def _history_hours(hass: Hass, spec: dict[str, Any], days: int) -> str:
    entities = spec.get("entities") or []
    if not entities:
        return NO_DATA
    try:
        totals = hass.seconds_in_state(entities, spec.get("state", "playing"), window_start(days))
    except Exception as exc:  # noqa: BLE001 - a stat must never break the render
        log.warning("history for %s failed: %s", spec.get("label"), exc)
        return NO_DATA
    if not totals:
        return NO_DATA
    return _hours_minutes(sum(totals.values()))


def _pair(states: dict[str, State], spec: dict[str, Any]) -> tuple[str, str]:
    """One number per person, in `config.people` order.

    Tolerates a single entity so a head-to-head can be set up one phone at a
    time: Ed's steps show on their own until Hannah's sensor exists, rather than
    the whole row sitting at a dash waiting for it -- the second column just
    reads NO_DATA until then.
    """
    entities = (spec.get("entities") or [])[:2]
    values = []
    for entity in entities:
        state = states.get(entity)
        number = state.number() if state and not state.missing else None
        values.append(_compact(number) if number is not None else NO_DATA)
    while len(values) < 2:
        values.append(NO_DATA)
    return (values[0], values[1])


def _sum(states: dict[str, State], spec: dict[str, Any]) -> str:
    entities = spec.get("entities") or []
    total = 0.0
    seen = False
    unit = spec.get("unit")
    for entity in entities:
        state = states.get(entity)
        number = state.number() if state and not state.missing else None
        if number is None:
            continue
        total += number
        seen = True
        unit = unit or state.attr("unit_of_measurement")
    if not seen:
        return NO_DATA
    return f"{round(total)} {unit}".strip()


def _spotify_pair(config: Config) -> tuple[str, str]:
    values = [spotify.poll(config, person.key) for person in config.people[:2]]
    while len(values) < 2:
        values.append(NO_DATA)
    return (values[0], values[1])


def build(
    config: Config,
    hass: Hass,
    states: dict[str, State],
    *,
    days: int = 7,
) -> list[Stat]:
    out: list[Stat] = []
    for spec in config.stats[:4]:
        kind = spec.get("kind")
        label = spec.get("label", "?")
        if kind == "history_hours":
            out.append(Stat(label=label, value=_history_hours(hass, spec, days)))
        elif kind == "pair":
            out.append(Stat(label=label, pair=_pair(states, spec)))
        elif kind == "sum_energy":
            out.append(Stat(label=label, value=_sum(states, spec)))
        elif kind == "spotify_hours":
            out.append(Stat(label=label, pair=_spotify_pair(config)))
        else:
            log.warning("unknown stat kind %r for %r", kind, label)
            out.append(Stat(label=label, value=NO_DATA))
    return out
