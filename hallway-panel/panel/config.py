"""Load and validate panel.yaml.

Deliberately thin: this resolves paths and fails loudly on the handful of things
that would otherwise produce a silently wrong panel (a workplace key that does
not exist, a bin the waste sensor never reports). Everything else is left as
plain dicts so adding a config key does not mean touching this file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def _parse_time(value: str, field: str) -> time:
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, AttributeError) as exc:
        raise ConfigError(f"{field}: expected HH:MM, got {value!r}") from exc


@dataclass
class Person:
    key: str
    name: str
    badge: str
    person: str
    calendar: str | None


class Config:
    def __init__(self, raw: dict[str, Any], path: Path):
        self.raw = raw
        self.path = path

        self.panel = raw.get("panel", {})
        self.weather = raw.get("weather", {})
        self.commute = raw.get("commute", {})
        self.waste = raw.get("waste", {})
        self.alerts = raw.get("alerts", {})
        self.calendar = raw.get("calendar", {})
        self.stats = raw.get("stats", [])
        self.refresh = raw.get("refresh", {})

        ha = raw.get("home_assistant", {})
        # Inside the add-on the Supervisor provides both of these, and they
        # differ from anything sensible to write in a file, so the environment
        # wins over the config. Running from a checkout, neither is set and the
        # file's values apply.
        self.base_url = (
            os.environ.get("HA_BASE_URL") or str(ha.get("base_url", ""))
        ).rstrip("/")
        self.timezone = ha.get("timezone", "Europe/London")
        self._token_env = ha.get("token_env", "HA_TOKEN")

        self.people = [
            Person(
                key=entry["key"],
                name=entry["name"],
                badge=entry["badge"],
                person=entry["person"],
                calendar=entry.get("calendar"),
            )
            for entry in raw.get("people", [])
        ]

        self._validate()

    # ------------------------------------------------------------ accessors

    @property
    def token(self) -> str:
        # SUPERVISOR_TOKEN is what the add-on gets for free; the configured
        # variable is for running against a remote instance from a checkout.
        token = os.environ.get(self._token_env) or os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            raise ConfigError(
                f"No Home Assistant token. Set ${self._token_env} to a long-lived "
                f"access token (Profile -> Security -> Long-lived access tokens). "
                f"Inside the add-on this comes from the Supervisor automatically."
            )
        return token

    @property
    def calendar_sources(self) -> list[tuple[str, str]]:
        """(badge, calendar entity) for everything the agenda should read.

        People contribute their own calendar; `calendar.extra` covers the ones
        with nobody behind them -- a shared family calendar, birthdays -- which
        still want a badge so the panel can say whose thing it is.
        """
        sources = [(p.badge, p.calendar) for p in self.people if p.calendar]
        for entry in self.calendar.get("extra", []) or []:
            if entry.get("entity"):
                sources.append((entry.get("badge", "·"), entry["entity"]))
        return sources

    def person(self, key: str) -> Person:
        for entry in self.people:
            if entry.key == key:
                return entry
        raise ConfigError(f"No person with key {key!r} in panel.yaml")

    @property
    def ed_workplace(self) -> dict[str, Any]:
        """The workplace Ed is currently commuting to."""
        key = self.commute["ed_workplace"]
        return self.commute["workplaces"][key]

    @property
    def rain_style(self) -> str:
        return self.panel.get("rain_style", "density")

    def rule_time(self, name: str) -> time:
        return _parse_time(self.commute["rules"][name], f"commute.rules.{name}")

    # ----------------------------------------------------------- validation

    def _validate(self) -> None:
        if not self.base_url:
            raise ConfigError("home_assistant.base_url is required")

        if not self.people:
            raise ConfigError("at least one entry under `people` is required")

        badges = [p.badge for p in self.people]
        if len(set(badges)) != len(badges):
            raise ConfigError(f"person badges must be unique, got {badges}")

        workplaces = self.commute.get("workplaces", {})
        chosen = self.commute.get("ed_workplace")
        if chosen not in workplaces:
            raise ConfigError(
                f"commute.ed_workplace is {chosen!r}, which is not one of "
                f"{sorted(workplaces)}. Change it here to switch offices."
            )

        for name in ("bike_cutoff", "hide_after", "hannah_solo_from"):
            self.rule_time(name)

        style = self.rain_style
        if style not in ("density", "columns", "ribbon"):
            raise ConfigError(
                f"panel.rain_style is {style!r}; expected density, columns or ribbon"
            )


def load(path: str | Path | None = None) -> Config:
    """Load panel.yaml.

    The add-on points $PANEL_CONFIG at /config/panel.yaml, which the Supervisor
    surfaces as /addon_configs/<slug>/panel.yaml on the host -- editable with the
    File editor add-on and, unlike a copy baked into the image, surviving an
    add-on rebuild.
    """
    resolved = Path(path or os.environ.get("PANEL_CONFIG") or ROOT / "panel.yaml")
    if not resolved.is_file():
        raise ConfigError(f"No config at {resolved}")
    with resolved.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return Config(raw, resolved)
