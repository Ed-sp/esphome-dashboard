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
    people: list[Person],
    tz: ZoneInfo,
    *,
    count: int = 4,
    days_ahead: int = 14,
) -> list[Event]:
    now = datetime.now(tz)
    end = now + timedelta(days=days_ahead)

    seen: dict[tuple[str, str], Event] = {}
    ordered: list[tuple[datetime, Event]] = []

    for person in people:
        if not person.calendar:
            continue
        for raw in hass.calendar_events(person.calendar, now, end):
            title = (raw.get("summary") or "").strip()
            if not title:
                continue
            start, all_day = _parse(raw.get("start"), tz)
            if start is None or start < now - timedelta(hours=1):
                continue

            key = (start.isoformat(), title.lower())
            if key in seen:
                continue

            event = Event(
                badge=person.badge,
                when=_when_label(start, all_day, now),
                title=title,
            )
            seen[key] = event
            ordered.append((start, event))

    ordered.sort(key=lambda pair: pair[0])
    return [event for _, event in ordered[:count]]
