"""What the layout draws.

Deliberately free of Home Assistant concepts. Everything here is already
resolved, formatted and ordered -- the renderer makes no decisions about which
commute applies or whether the bin goes out, it only draws what it is handed.
That keeps the rule engine testable without a display, and means the same model
could feed a JSON-and-lambdas board if that ever comes back on the table.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Now:
    temperature: float
    condition: str
    summary: str
    feels_like: float | None = None
    sunset: str | None = None
    night: bool = False


@dataclass
class Day:
    label: str
    condition: str
    high: float
    low: float
    rain: float | None = None


@dataclass
class Hour:
    hour: int
    temperature: float
    rain: float | None = None
    night: bool = False


@dataclass
class Commute:
    who: str
    destination: str
    mode: str  # "bike" | "car"
    minutes: int
    delta_minutes: int | None = None  # positive = slower than usual
    note: str | None = None

    @property
    def slow(self) -> bool:
        return self.delta_minutes is not None and self.delta_minutes > 0


@dataclass
class Alert:
    text: str
    icon: str = "battery"
    urgent: bool = False  # urgent alerts get the inverted bar


@dataclass
class Event:
    badge: str
    when: str
    title: str


@dataclass
class Stat:
    label: str
    value: str


@dataclass
class Collect:
    title: str
    text: str


@dataclass
class Panel:
    date_label: str
    now: Now
    week: list[Day] = field(default_factory=list)
    hours: list[Hour] = field(default_factory=list)
    rain_summary: str = ""
    commutes: list[Commute] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    sky: str | None = None
    stats: list[Stat] = field(default_factory=list)
    collect: Collect | None = None
