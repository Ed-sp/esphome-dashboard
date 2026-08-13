"""Current conditions, the hourly trace, and the seven-day list."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..hass import Hass, State
from ..model import Day, Hour, Now

log = logging.getLogger(__name__)


def _parse(value: str | None, tz: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(tz)


def _sun_times(states: dict[str, State], tz: ZoneInfo) -> tuple[int, int]:
    """(sunrise hour, sunset hour) in local time, for choosing night icons."""
    sun = states.get("sun.sun")
    rising = _parse(sun.attr("next_rising") if sun else None, tz)
    setting = _parse(sun.attr("next_setting") if sun else None, tz)
    return (rising.hour if rising else 6, setting.hour if setting else 21)


def now_block(states: dict[str, State], entity: str, tz: ZoneInfo) -> Now:
    weather = states.get(entity)
    if weather is None:
        raise RuntimeError(f"{entity} not found; check weather.entity in config.yaml")

    sun = states.get("sun.sun")
    setting = _parse(sun.attr("next_setting") if sun else None, tz)
    below_horizon = bool(sun and sun.state == "below_horizon")

    return Now(
        temperature=weather.attr("temperature", 0) or 0,
        condition=weather.state,
        summary=weather.state.replace("-", " ").replace("partlycloudy", "partly cloudy").capitalize(),
        feels_like=weather.attr("apparent_temperature"),
        sunset=setting.strftime("%H:%M") if setting else None,
        night=below_horizon,
    )


def hourly(
    hass: Hass, states: dict[str, State], entity: str, tz: ZoneInfo, count: int
) -> list[Hour]:
    forecast = hass.forecast(entity, "hourly")[:count]
    if not forecast:
        log.warning("%s returned no hourly forecast", entity)
        return []

    sunrise_hour, sunset_hour = _sun_times(states, tz)

    hours: list[Hour] = []
    for entry in forecast:
        when = _parse(entry.get("datetime"), tz)
        if when is None or entry.get("temperature") is None:
            continue
        hours.append(
            Hour(
                hour=when.hour,
                temperature=float(entry["temperature"]),
                rain=entry.get("precipitation_probability"),
                night=not (sunrise_hour <= when.hour < sunset_hour),
            )
        )
    return hours


def daily(hass: Hass, entity: str, tz: ZoneInfo, count: int = 7) -> list[Day]:
    forecast = hass.forecast(entity, "daily")[:count]
    today = datetime.now(tz).date()

    days: list[Day] = []
    for entry in forecast:
        when = _parse(entry.get("datetime"), tz)
        if when is None or entry.get("temperature") is None:
            continue
        days.append(
            Day(
                label="Today" if when.date() == today else when.strftime("%a"),
                condition=entry.get("condition", "cloudy"),
                high=float(entry["temperature"]),
                low=float(entry.get("templow") or entry["temperature"]),
                rain=entry.get("precipitation_probability"),
            )
        )
    return days


def summary(hours: list[Hour]) -> str:
    """The line above the graph: range, plus when the rain lands if it does."""
    if not hours:
        return ""

    temps = [h.temperature for h in hours]
    span = f"{round(min(temps))}–{round(max(temps))}°"

    wettest = max(hours, key=lambda h: h.rain or 0)
    if (wettest.rain or 0) < 20:
        return f"{span}  ·  DRY"
    return f"{span}  ·  RAIN {round(wettest.rain)}% AT {wettest.hour:02d}:00"


def rain_within(hours: list[Hour], minutes: int, threshold: int = 40) -> bool:
    """Is rain likely inside the next `minutes`? Used to decide bike vs car.

    Checking the current condition alone would send you out on a bike into a
    shower that starts as you reach the main road, so this looks across the whole
    ride window instead.
    """
    span = max(1, round(minutes / 60))
    return any((hour.rain or 0) >= threshold for hour in hours[:span])
