"""The "Needs you" block: bins, flat batteries, thirsty plants.

Ordered by urgency and capped, because the block has a fixed height and the
layout would otherwise run into the bottom band. The bin alert is the only one
allowed to fill solid black, which is what makes it readable from the far end of
the hall without being read.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import Config
from ..hass import State
from ..model import Alert

log = logging.getLogger(__name__)

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%d %B %Y", "%A %d %B")


def _parse_date(value: str, today: date) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        # Formats without a year land in 1900; pull them onto the current one.
        if parsed.year == 1900:
            parsed = parsed.replace(year=today.year)
        return parsed
    log.warning("could not parse a collection date from %r", text)
    return None


def waste(config: Config, states: dict[str, State], tz: ZoneInfo) -> Alert | None:
    """The bin alert, from the evening before until noon on collection day."""
    sensor = states.get(config.waste["sensor"])
    if sensor is None:
        return None

    now = datetime.now(tz)
    today = now.date()
    show_from = datetime.strptime(config.waste["show_from"], "%H:%M").time()
    hide_at = datetime.strptime(config.waste["hide_at"], "%H:%M").time()

    for attribute, meta in config.waste["bins"].items():
        when = _parse_date(str(sensor.attr(attribute, "")), today)
        if when is None:
            continue

        due_tonight = when == today + timedelta(days=1) and now.time() >= show_from
        due_today = when == today and now.time() < hide_at
        if not (due_tonight or due_today):
            continue

        label = meta["label"]
        return Alert(
            text=f"{label} out {'tonight' if due_tonight else 'this morning'}",
            icon=meta.get("icon", "bin"),
            urgent=True,
        )

    if all(not str(sensor.attr(name, "")).strip() for name in config.waste["bins"]):
        # The integration is running but reporting nothing. Worth saying out loud
        # rather than silently never showing a bin alert again.
        log.warning(
            "%s has no collection dates in any of %s -- the scraper is running but "
            "returning empty values, so bin alerts will never fire",
            config.waste["sensor"],
            ", ".join(config.waste["bins"]),
        )
    return None


def batteries(config: Config, states: dict[str, State]) -> list[Alert]:
    threshold = config.alerts.get("battery_below", 20)
    found: list[tuple[float, Alert]] = []

    for entity_id, state in states.items():
        if not entity_id.startswith("sensor.") or state.missing:
            continue
        if state.attr("device_class") != "battery":
            continue
        level = state.number()
        if level is None or level >= threshold:
            continue
        name = state.attr("friendly_name", entity_id)
        name = name.replace(" Battery", "").replace(" battery", "")
        found.append((level, Alert(text=f"{name} battery at {round(level)}%", icon="battery")))

    found.sort(key=lambda pair: pair[0])
    return [alert for _, alert in found]


def panel_health(config: Config, states: dict[str, State]) -> list[Alert]:
    """The panel's own battery and signal, which stay silent until they matter."""
    out: list[Alert] = []

    battery_entity = config.alerts.get("panel_battery_entity")
    if battery_entity:
        state = states.get(battery_entity)
        level = state.number() if state and not state.missing else None
        if level is not None and level < config.alerts.get("panel_battery_below", 10):
            out.append(Alert(text=f"Panel battery at {round(level)}%", icon="battery"))

    rssi_entity = config.alerts.get("panel_rssi_entity")
    if rssi_entity:
        state = states.get(rssi_entity)
        rssi = state.number() if state and not state.missing else None
        if rssi is not None and rssi < config.alerts.get("panel_rssi_below", -80):
            out.append(Alert(text=f"Panel signal weak ({round(rssi)} dBm)", icon="battery"))

    return out


def plants(config: Config, states: dict[str, State], tz: ZoneInfo) -> list[Alert]:
    """Watering reminders.

    Only fires for plants with a configured sensor. A plant with nothing but a
    watering interval has no last-watered date to count from, so guessing would
    put a permanent nag on the wall.
    """
    out: list[Alert] = []
    for plant in config.alerts.get("plants", []) or []:
        sensor = plant.get("sensor")
        if not sensor:
            continue
        state = states.get(sensor)
        if state is None or state.missing:
            continue
        moisture = state.number()
        if moisture is not None and moisture < plant.get("moisture_below", 25):
            out.append(Alert(text=f"{plant['name']} needs water", icon="leaf"))
    return out


def build(config: Config, states: dict[str, State], tz: ZoneInfo) -> list[Alert]:
    out: list[Alert] = []

    bin_alert = waste(config, states, tz)
    if bin_alert:
        out.append(bin_alert)

    out.extend(plants(config, states, tz))
    out.extend(panel_health(config, states))
    out.extend(batteries(config, states))

    return out[: config.alerts.get("max_lines", 3)]
