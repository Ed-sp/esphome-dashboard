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

def waste(config: Config, hass, tz: ZoneInfo) -> Alert | None:
    """The bin alert, from the evening before until noon on collection day.

    Read from the waste calendar rather than the sensor. The sensor's attributes
    are keyed by *date* with the waste type as the value -- so the keys change
    every collection, and matching on them would mean rewriting config
    fortnightly. The calendar gives a stable (date, summary) pair.

    What the council calls each collection is matched to what the panel says via
    `waste.types` in panel.yaml, because "Non-recyclable refuse waste" is not
    what anyone would want across a hallway.
    """
    entity = config.waste.get("calendar")
    if not entity:
        return None

    now = datetime.now(tz)
    today = now.date()
    show_from = datetime.strptime(config.waste["show_from"], "%H:%M").time()
    hide_at = datetime.strptime(config.waste["hide_at"], "%H:%M").time()

    events = hass.calendar_events(entity, now - timedelta(days=1), now + timedelta(days=3))
    if not events:
        log.info("%s has no collections in the next few days", entity)
        return None

    for raw in events:
        start = (raw.get("start") or {}).get("date")
        summary = (raw.get("summary") or "").strip()
        if not start or not summary:
            continue
        try:
            when = date.fromisoformat(start)
        except ValueError:
            continue

        due_tonight = when == today + timedelta(days=1) and now.time() >= show_from
        due_today = when == today and now.time() < hide_at
        if not (due_tonight or due_today):
            continue

        meta = _waste_type(config, summary)
        if meta is None or not meta.get("show", True):
            continue

        return Alert(
            text=f"{meta['label']} out {'tonight' if due_tonight else 'this morning'}",
            icon=meta.get("icon", "bin"),
            urgent=True,
        )

    return None


def _waste_type(config: Config, summary: str) -> dict | None:
    """Match the council's wording to a panel label.

    `exclude` is not decoration. The Vale calls a rubbish week "Non-recyclable
    refuse waste", which contains "recycl" -- so a plain substring match on the
    recycling rule tells you to put the wrong bin out. Getting that wrong is
    worse than showing nothing, since the panel would be actively lying on the
    one alert it fills the screen black for.
    """
    lowered = summary.lower()
    for entry in config.waste.get("types", []) or []:
        needle = str(entry.get("match", "")).lower()
        if not needle or needle not in lowered:
            continue
        excluded = [str(x).lower() for x in _as_list(entry.get("exclude"))]
        if any(x in lowered for x in excluded):
            continue
        return entry

    log.warning(
        "no waste.types entry matches %r, so no bin alert will show for it", summary
    )
    return None


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


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


def build(config: Config, hass, states: dict[str, State], tz: ZoneInfo) -> list[Alert]:
    out: list[Alert] = []

    bin_alert = waste(config, hass, tz)
    if bin_alert:
        out.append(bin_alert)

    out.extend(plants(config, states, tz))
    out.extend(panel_health(config, states))
    out.extend(batteries(config, states))

    return out[: config.alerts.get("max_lines", 3)]
