"""One line about the sky, when there is something worth going outside for.

Three ingredients, none of which need the network:

*   **Eclipses** and **meteor showers** come from data/sky.yaml. Shower peaks
    land within a day of the same date each year and eclipse dates are known
    centuries ahead, so fetching them would buy nothing and add a failure mode.
*   **Moon phases** are computed, using Meeus chapter 49.

On that last point: the obvious approach is to take the mean synodic month and
count forward from a known new moon. That is wrong by up to fourteen hours,
because the Moon's orbit is eccentric, which is enough to name the wrong day
surprisingly often. The periodic corrections below bring it inside a few
minutes.

The whole thing is validated by a pleasing coincidence: solar eclipses only
happen at new moon and lunar eclipses only at full moon, so the verified eclipse
dates in sky.yaml double as test vectors for the phase calculation.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[2] / "data"

NEW_MOON, FULL_MOON = 0.0, 0.5


@lru_cache(maxsize=1)
def _tables() -> dict[str, Any]:
    path = DATA / "sky.yaml"
    if not path.is_file():
        log.warning("%s is missing; the sky line will stay empty", path)
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


# --------------------------------------------------------------- moon phase


def _julian(when: datetime) -> float:
    ts = when.astimezone(timezone.utc).timestamp()
    return ts / 86400.0 + 2440587.5


def _from_julian(jde: float) -> datetime:
    return datetime.fromtimestamp((jde - 2440587.5) * 86400.0, tz=timezone.utc)


def _phase_jde(k: float) -> float:
    """Julian Ephemeris Day of the phase indexed by `k` (Meeus 49.1 and 49.4).

    Integer k is a new moon, k + 0.5 the following full moon. Only the larger
    periodic terms are kept; the rest move the answer by seconds.
    """
    t = k / 1236.85
    jde = (
        2451550.09766
        + 29.530588861 * k
        + 0.00015437 * t**2
        - 0.000000150 * t**3
        + 0.00000000073 * t**4
    )

    e = 1 - 0.002516 * t - 0.0000074 * t**2
    rad = math.radians

    # Sun's mean anomaly, Moon's mean anomaly, Moon's argument of latitude, and
    # the longitude of the ascending node.
    m = rad(2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3)
    mp = rad(
        201.5643 + 385.81693528 * k + 0.0107582 * t**2 + 0.00001238 * t**3 - 0.000000058 * t**4
    )
    f = rad(
        160.7108 + 390.67050284 * k - 0.0016118 * t**2 - 0.00000227 * t**3 + 0.000000011 * t**4
    )
    omega = rad(124.7746 - 1.56375588 * k + 0.0020672 * t**2 + 0.00000215 * t**3)

    is_full = abs(k - math.floor(k) - 0.5) < 1e-6
    lead, solar, second = (
        (-0.40614, 0.17302, 0.01614) if is_full else (-0.40720, 0.17241, 0.01608)
    )

    jde += (
        lead * math.sin(mp)
        + solar * e * math.sin(m)
        + second * math.sin(2 * mp)
        + 0.01043 * math.sin(2 * f)
        + 0.00734 * e * math.sin(mp - m)
        - 0.00515 * e * math.sin(mp + m)
        + 0.00209 * e**2 * math.sin(2 * m)
        - 0.00111 * math.sin(mp - 2 * f)
        - 0.00057 * math.sin(mp + 2 * f)
        + 0.00056 * e * math.sin(2 * mp + m)
        - 0.00042 * math.sin(3 * mp)
        + 0.00042 * e * math.sin(m + 2 * f)
        + 0.00038 * e * math.sin(m - 2 * f)
        - 0.00024 * e * math.sin(2 * mp - m)
        - 0.00017 * math.sin(omega)
        - 0.00007 * math.sin(mp + 2 * m)
    )
    return jde


def next_phase(after: datetime, phase: float = FULL_MOON) -> datetime:
    """The first new (phase=0.0) or full (0.5) moon strictly after `after`."""
    years = (after - datetime(2000, 1, 1, tzinfo=timezone.utc)).days / 365.25
    k = math.floor(years * 12.3685) - 2

    for _ in range(6):
        when = _from_julian(_phase_jde(k + phase))
        if when > after:
            return when
        k += 1
    raise RuntimeError("could not bracket the next lunar phase")


# ------------------------------------------------------------------- events


@dataclass
class SkyEvent:
    when: date
    text: str
    rank: int


def _when_word(target: date, today: date, *, night: bool = False) -> str:
    days = (target - today).days
    if days == 0:
        return "tonight" if night else "today"
    if days == 1:
        return "tomorrow night" if night else "tomorrow"
    # A bare weekday name a full week out reads as *this* coming one, which on
    # the matching weekday is worse than useless.
    if days >= 7:
        return f"next {target.strftime('%A')}"
    return target.strftime("%A")


def _showers(today: date, horizon: date) -> list[SkyEvent]:
    out: list[SkyEvent] = []
    for entry in _tables().get("showers") or []:
        month, day = (int(part) for part in str(entry["peak"]).split("-"))
        for year in {today.year, horizon.year}:
            try:
                peak = date(year, month, day)
            except ValueError:
                continue
            if not (today <= peak <= horizon):
                continue
            note = entry.get("note")
            text = f"{entry['name']} peak {_when_word(peak, today, night=True)}"
            out.append(SkyEvent(peak, f"{text}, {note}" if note else text, entry.get("rank", 3)))
    return out


def _eclipses(today: date, horizon: date) -> list[SkyEvent]:
    out: list[SkyEvent] = []
    for entry in _tables().get("eclipses") or []:
        when = entry["date"]
        if isinstance(when, str):
            when = date.fromisoformat(when)
        if not (today <= when <= horizon):
            continue

        parts = [f"{entry['kind']} {_when_word(when, today)}"]
        if entry.get("time"):
            parts.append(entry["time"])
        if entry.get("note"):
            parts.append(entry["note"])
        out.append(SkyEvent(when, ", ".join(parts), entry.get("rank", 8)))
    return out


def _full_moon(today: date, horizon: date, tz) -> list[SkyEvent]:
    start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    when = next_phase(start, FULL_MOON).astimezone(tz).date()
    if not (today <= when <= horizon):
        return []
    return [SkyEvent(when, f"Full moon {_when_word(when, today)}", 1)]


def line(today: date | None = None, *, days: int = 7, tz=timezone.utc) -> str | None:
    """The single most interesting thing happening in the next `days`, or None.

    Returning None is normal and the layout drops the line entirely -- most weeks
    genuinely have nothing worth walking outside for.
    """
    today = today or date.today()
    horizon = today + timedelta(days=days)

    events = _eclipses(today, horizon) + _showers(today, horizon) + _full_moon(today, horizon, tz)
    if not events:
        return None

    # Rank first, then soonest, so a total eclipse next week outranks tonight's
    # full moon but two eclipses in a week show the nearer one.
    events.sort(key=lambda event: (-event.rank, event.when))
    return events[0].text
