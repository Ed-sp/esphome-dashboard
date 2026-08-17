"""The sky line: one thing worth going outside for, or nothing at all.

Events come from independent *providers*. A provider is a function that takes a
`Context` and returns `SkyEvent`s; it is registered by name with `@provider` and
gets its own block in `panel.yaml`, so any of them can be switched off without
touching code:

    sky:
      events:
        aurora: { enabled: true, threshold: amber }
        iss:    { enabled: false }

Adding one means writing a function in this package, decorating it, and
importing it at the bottom of this file. Nothing else needs to know it exists.

Three properties worth preserving if you edit this:

*   **A provider that raises loses only itself.** The others still contribute.
    A hallway panel that renders nothing because a satellite API changed its
    JSON would be a bad trade.
*   **Rank is comparable across providers.** They are competing for one line, so
    the numbers only mean anything relative to each other. See RANKS below.
*   **Returning nothing is the normal case.** On most days of the year every
    provider is silent and the layout drops the line entirely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta, timezone
from typing import Any, Callable

log = logging.getLogger(__name__)

# A shared scale, so providers can be compared. Roughly: how likely is this to
# make someone put their shoes on?
RANKS = {
    "spectacle": 12,  # rare, happening now, visible from here -- a red aurora
    "eclipse_total": 10,
    "eclipse_partial": 8,
    "alert": 9,  # a live alert that is worth a look
    "shower_major": 7,  # Perseids, Geminids, Quadrantids
    "shower_minor": 3,
    "routine": 1,  # the full moon, which comes round every month
}


@dataclass
class SkyEvent:
    when: date
    text: str
    rank: int


@dataclass
class Context:
    """Everything a provider is allowed to depend on."""

    today: date
    horizon: date
    tz: Any = timezone.utc
    settings: dict[str, Any] = field(default_factory=dict)

    def within(self, when: date) -> bool:
        return self.today <= when <= self.horizon

    def when_word(self, target: date, *, night: bool = False) -> str:
        """'tonight', 'tomorrow', 'Friday', 'next Friday'."""
        days = (target - self.today).days
        if days == 0:
            return "tonight" if night else "today"
        if days == 1:
            return "tomorrow night" if night else "tomorrow"
        # A bare weekday name a full week out reads as *this* coming one, which
        # on the matching weekday is worse than useless.
        if days >= 7:
            return f"next {target.strftime('%A')}"
        return target.strftime("%A")


Provider = Callable[[Context], list[SkyEvent]]

_REGISTRY: dict[str, Provider] = {}


def provider(name: str) -> Callable[[Provider], Provider]:
    def register(fn: Provider) -> Provider:
        if name in _REGISTRY:
            raise ValueError(f"two sky providers are both called {name!r}")
        _REGISTRY[name] = fn
        return fn

    return register


def providers() -> list[str]:
    return sorted(_REGISTRY)


def collect_events(
    today: date | None = None,
    *,
    days: int = 7,
    tz=timezone.utc,
    config: dict[str, Any] | None = None,
) -> list[SkyEvent]:
    """Every event every enabled provider has to offer, best first."""
    today = today or date.today()
    config = config or {}
    horizon = today + timedelta(days=days)

    events: list[SkyEvent] = []
    for name, fn in _REGISTRY.items():
        settings = config.get(name) or {}
        if not settings.get("enabled", True):
            continue
        context = Context(today=today, horizon=horizon, tz=tz, settings=settings)
        try:
            events.extend(fn(context))
        except Exception as exc:  # noqa: BLE001 - one provider must not sink the rest
            log.warning("sky provider %r failed: %s", name, exc)

    # Rank first, then soonest: a total eclipse next week outranks tonight's full
    # moon, but two eclipses in one week show the nearer.
    events.sort(key=lambda event: (-event.rank, event.when))
    return events


def line(
    today: date | None = None,
    *,
    days: int = 7,
    tz=timezone.utc,
    config: dict[str, Any] | None = None,
) -> str | None:
    events = collect_events(today, days=days, tz=tz, config=config)
    return events[0].text if events else None


# Importing these registers them. Order is irrelevant -- rank decides what wins.
from . import almanac, aurora, moon  # noqa: E402,F401
