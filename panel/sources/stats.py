"""The four numbers in the bottom-right block.

Two of the three kinds work off history rather than a dedicated sensor, which is
what lets telly and music hours run today without adding an integration or a
scrobbler: the Fire TV and Sonos players already record when they were playing.

A slot with no data renders an em dash rather than disappearing, so the block
keeps its shape and the panel does not reflow week to week.
"""

from __future__ import annotations

import logging
from typing import Any

from ..hass import Hass, State, window_start
from ..model import Stat

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


def _pair(states: dict[str, State], spec: dict[str, Any]) -> str:
    entities = spec.get("entities") or []
    if len(entities) < 2:
        return NO_DATA
    values = []
    for entity in entities[:2]:
        state = states.get(entity)
        number = state.number() if state and not state.missing else None
        values.append(_compact(number) if number is not None else NO_DATA)
    return " / ".join(values)


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


def build(
    hass: Hass,
    states: dict[str, State],
    specs: list[dict[str, Any]],
    *,
    days: int = 7,
) -> list[Stat]:
    out: list[Stat] = []
    for spec in specs[:4]:
        kind = spec.get("kind")
        if kind == "history_hours":
            value = _history_hours(hass, spec, days)
        elif kind == "pair":
            value = _pair(states, spec)
        elif kind == "sum_energy":
            value = _sum(states, spec)
        else:
            log.warning("unknown stat kind %r for %r", kind, spec.get("label"))
            value = NO_DATA
        out.append(Stat(label=spec.get("label", "?"), value=value))
    return out
