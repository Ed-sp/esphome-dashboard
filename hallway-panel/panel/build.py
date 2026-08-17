"""Assemble a Panel from live Home Assistant state.

One `/api/states` snapshot feeds everything that can be answered from current
state; only forecasts, calendars and history need their own round trips. Each
section is guarded independently, because a panel missing its stats is far more
useful than a panel that failed to render.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Config
from .hass import Hass
from .model import Panel
from .sources import agenda, alerts, collect, commute, sky, stats, weather

log = logging.getLogger(__name__)


def _date_label(tz: ZoneInfo) -> str:
    now = datetime.now(tz)
    # %-d is glibc-only and %#d is Windows-only, so strip the pad by hand.
    return f"{now.strftime('%A')} {now.day} {now.strftime('%B')}"


def _sky_line(config: Config, tz: ZoneInfo) -> str | None:
    """Whichever enabled sky provider has the most interesting thing to say."""
    settings = config.raw.get("sky", {}) or {}
    return sky.line(
        datetime.now(tz).date(),
        days=settings.get("lookahead_days", 7),
        tz=tz,
        config=settings.get("events") or {},
    )


def build(config: Config, hass: Hass) -> Panel:
    tz = ZoneInfo(config.timezone)
    states = hass.states()

    entity = config.weather["entity"]
    now_block = weather.now_block(states, entity, tz)

    def guarded(name: str, fn, fallback):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - one bad section must not blank the panel
            log.warning("%s section failed: %s", name, exc, exc_info=log.isEnabledFor(logging.DEBUG))
            return fallback

    hours = guarded(
        "hourly forecast",
        lambda: weather.hourly(hass, states, entity, tz, config.weather.get("hours", 24)),
        [],
    )
    week = guarded("daily forecast", lambda: weather.daily(hass, states, entity, tz), [])

    return Panel(
        date_label=_date_label(tz),
        now=now_block,
        week=week,
        hours=hours,
        rain_summary=weather.summary(hours),
        commutes=guarded("commute", lambda: commute.build(config, states, hours, tz), []),
        alerts=guarded("alerts", lambda: alerts.build(config, hass, states, tz), []),
        events=guarded(
            "calendar",
            lambda: agenda.upcoming(
                hass,
                config.calendar_sources,
                tz,
                count=config.calendar.get("count", 4),
                days_ahead=config.calendar.get("days_ahead", 14),
            ),
            [],
        ),
        sky=guarded("sky", lambda: _sky_line(config, tz), None),
        stats=guarded("stats", lambda: stats.build(hass, states, config.stats), []),
        collect=guarded("collect", lambda: collect.for_date(datetime.now(tz).date()), None),
    )
