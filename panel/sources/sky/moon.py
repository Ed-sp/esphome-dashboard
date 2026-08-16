"""Moon phase, computed rather than fetched.

The tempting shortcut is to take the mean synodic month and count forward from a
known new moon. That is wrong by up to fourteen hours, because the Moon's orbit
is eccentric, which names the wrong day often enough to matter on something read
in passing. The periodic terms from Meeus chapter 49 bring it inside a few
minutes.

It validates itself pleasingly: solar eclipses only happen at new moon and lunar
eclipses only at full moon, so the verified eclipse dates in data/sky.yaml serve
as test vectors for this file.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from . import RANKS, Context, SkyEvent, provider

NEW_MOON, FULL_MOON = 0.0, 0.5


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


@provider("moon")
def upcoming(context: Context) -> list[SkyEvent]:
    start = datetime.combine(context.today, datetime.min.time(), tzinfo=timezone.utc)
    when = next_phase(start, FULL_MOON).astimezone(context.tz).date()
    if not context.within(when):
        return []
    return [
        SkyEvent(when, f"Full moon {context.when_word(when)}", RANKS["routine"]),
    ]
