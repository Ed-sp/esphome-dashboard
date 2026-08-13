"""Which commute the panel shows, and whether it is slower than usual.

The rules, evaluated top to bottom, first match wins:

1.  After `hide_after`, or nobody home         -> nothing at all
2.  Before `bike_cutoff`, Ed home, dry         -> Ed by bike (+ Hannah if home)
3.  Before `bike_cutoff`, Ed home, rain        -> Ed by car  (+ Hannah if home)
4.  Between the two, Ed home                   -> one combined car journey
5.  Ed away, Hannah home                       -> Hannah direct

Rules 5 and 6 from the design brief collapse into one: whether it is before or
after `hannah_solo_from` makes no difference to what is drawn, only to the
reasoning, since there is no combined trip to wait for either way.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Config
from ..hass import State
from ..model import Commute, Hour
from . import weather as weather_source

log = logging.getLogger(__name__)


def _minutes(states: dict[str, State], entity: str | None) -> int | None:
    if not entity:
        return None
    state = states.get(entity)
    if state is None or state.missing:
        return None
    value = state.number()
    return round(value) if value is not None else None


def _delta(config: Config, states: dict[str, State], key: str, actual: int) -> int | None:
    """How much slower than usual, or None if it is not worth mentioning.

    Stays silent until the baseline sensor has a value, rather than guessing --
    a statistics sensor reports nothing until it has history.
    """
    baseline = _minutes(states, config.commute.get("baselines", {}).get(key))
    if baseline is None or baseline <= 0:
        return None

    over = actual - baseline
    rules = config.commute["rules"]
    threshold = max(baseline * rules["slow_pct"] / 100, rules["slow_minutes"])
    return over if over >= threshold else None


def _leg(
    config: Config,
    states: dict[str, State],
    key: str,
    who: str,
    destination: str,
    mode: str,
    note: str | None = None,
) -> Commute | None:
    minutes = _minutes(states, config.commute.get("sensors", {}).get(key))
    if minutes is None:
        log.info("no travel time for %s; skipping that leg", key)
        return None
    return Commute(
        who=who,
        destination=destination,
        mode=mode,
        minutes=minutes,
        delta_minutes=_delta(config, states, key, minutes),
        note=note,
    )


def _at_home(states: dict[str, State], entity: str) -> bool:
    state = states.get(entity)
    return bool(state and state.state == "home")


def build(
    config: Config,
    states: dict[str, State],
    hours: list[Hour],
    tz: ZoneInfo,
) -> list[Commute]:
    now = datetime.now(tz).time()
    rules = config.commute["rules"]

    ed = config.person("ed")
    hannah = config.person("hannah")
    ed_home = _at_home(states, ed.person)
    hannah_home = _at_home(states, hannah.person)

    # Rule 1
    if now >= config.rule_time("hide_after") or not (ed_home or hannah_home):
        return []

    office = config.ed_workplace
    hannah_office = config.commute["hannah_workplace"]

    hannah_leg = (
        _leg(config, states, "hannah_car", hannah.name, hannah_office["label"], "car")
        if hannah_home
        else None
    )

    # Rule 5
    if not ed_home:
        return [leg for leg in (hannah_leg,) if leg]

    # Rule 4
    if now >= config.rule_time("bike_cutoff"):
        combined = _leg(
            config,
            states,
            "combined_car",
            "Both",
            f"{office['label']} → {hannah_office['label']}",
            "car",
            note="one trip",
        )
        return [leg for leg in (combined,) if leg]

    # Rules 2 and 3
    wet = weather_source.rain_within(hours, rules["ride_window_minutes"])
    if wet:
        ed_leg = _leg(config, states, "ed_car", ed.name, office["label"], "car", note="rain due")
    else:
        ed_leg = _leg(
            config,
            states,
            "ed_bike",
            ed.name,
            office["label"],
            "bike",
            note=f"dry until {rules['hide_after']}",
        )

    return [leg for leg in (ed_leg, hannah_leg) if leg]
