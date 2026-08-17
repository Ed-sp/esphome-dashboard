"""Upcoming events, merged across everyone's calendar.

Ed's and Hannah's Google calendars are shared with each other, so the same event
often appears on both. Duplicates are collapsed on (start, title) and keep the
first badge seen, otherwise every shared appointment would take two of the four
slots on the panel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import Person
from ..hass import Hass
from ..model import Event

log = logging.getLogger(__name__)


def _parse(node: dict | str | None, tz: ZoneInfo) -> tuple[datetime | None, bool]:
    """Returns (local datetime, all_day). Calendar API gives date OR dateTime."""
    if isinstance(node, str):
        raw, all_day = node, "T" not in node
    elif isinstance(node, dict):
        if "dateTime" in node:
            raw, all_day = node["dateTime"], False
        elif "date" in node:
            raw, all_day = node["date"], True
        else:
            return None, False
    else:
        return None, False

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, all_day

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz), all_day


def _is_past(start: datetime, all_day: bool, now: datetime) -> bool:
    """Has this stopped being worth showing?

    All-day events begin at midnight, so comparing them against the clock drops
    today's from mid-morning onwards -- an all-day thing is still on all day.
    They are judged by date; timed events keep an hour's grace so something that
    has just started is still on the panel while you are looking for it.
    """
    if all_day:
        return start.date() < now.date()
    return start < now - timedelta(hours=1)


def _when_label(when: datetime, all_day: bool, now: datetime) -> str:
    days_away = (when.date() - now.date()).days

    if all_day:
        if days_away == 0:
            return "Today"
        if days_away == 1:
            return "Tomorrow"
        return when.strftime("%a %-d %b") if _supports_dash() else when.strftime("%a %d %b")

    clock = when.strftime("%H:%M")
    if days_away == 0:
        return f"{'Tonight' if when.hour >= 17 else 'Today'} {clock}"
    if days_away == 1:
        return f"Tomorrow {clock}"
    if days_away < 7:
        return f"{when.strftime('%a')} {clock}"
    return f"{when.strftime('%a %d %b')} {clock}"


def _supports_dash() -> bool:
    """`%-d` is glibc-only; Windows needs `%#d` or a plain zero-padded day."""
    try:
        datetime.now().strftime("%-d")
        return True
    except ValueError:
        return False


def upcoming(
    hass: Hass,
    sources: list[tuple[str, str]],
    tz: ZoneInfo,
    *,
    count: int = 4,
    days_ahead: int = 14,
) -> list[Event]:
    """Merge (badge, calendar entity) pairs into one ordered list.

    Order matters: the first source to claim an event keeps it. People come
    before the shared calendars in config, so a family event that also lands in
    someone's own calendar is badged to the person rather than the household.
    """
    now = datetime.now(tz)
    end = now + timedelta(days=days_ahead)

    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[datetime, Event]] = []

    for badge, entity in sources:
        for raw in hass.calendar_events(entity, now, end):
            title = (raw.get("summary") or "").strip()
            if not title:
                continue
            start, all_day = _parse(raw.get("start"), tz)
            if start is None or _is_past(start, all_day, now):
                continue

            key = (start.isoformat(), title.lower())
            if key in seen:
                continue

            seen.add(key)
            ordered.append(
                (start, Event(badge=badge, when=_when_label(start, all_day, now), title=title))
            )

    ordered.sort(key=lambda pair: pair[0])
    return [event for _, event in ordered[:count]]
