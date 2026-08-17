"""A small Home Assistant REST client.

Only the five calls the panel needs. Everything returns plain Python; nothing
here knows what a panel is.

Notes on the endpoints, because two of them are easy to get wrong:

*   Forecasts are no longer attributes on the weather entity. Since 2024.4 you
    have to call `weather.get_forecasts` and ask for the response, which over
    REST means the `?return_response` query parameter.
*   `/api/history/period` returns *state changes*, not durations. Time-in-state
    has to be integrated from the timestamps, and the first record is the state
    as it was at the window start rather than a change within it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15


class HassError(RuntimeError):
    pass


@dataclass
class State:
    entity_id: str
    state: str
    attributes: dict[str, Any]

    @property
    def missing(self) -> bool:
        return self.state in ("unknown", "unavailable", "")

    def number(self, default: float | None = None) -> float | None:
        try:
            return float(self.state)
        except (TypeError, ValueError):
            return default

    def attr(self, name: str, default: Any = None) -> Any:
        return self.attributes.get(name, default)


class Hass:
    def __init__(self, base_url: str, token: str, *, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}/api/{path.lstrip('/')}"
        try:
            response = self._session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise HassError(f"{method} {path} failed: {exc}") from exc

        if response.status_code == 401:
            raise HassError("Home Assistant rejected the token (401)")
        if not response.ok:
            raise HassError(f"{method} {path} returned {response.status_code}: {response.text[:200]}")

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    # -------------------------------------------------------------- states

    def states(self) -> dict[str, State]:
        """Every entity, in one call. Cheaper than N lookups and used as a snapshot."""
        payload = self._request("GET", "states")
        return {
            item["entity_id"]: State(item["entity_id"], item["state"], item.get("attributes") or {})
            for item in payload
        }

    def state(self, entity_id: str) -> State | None:
        try:
            item = self._request("GET", f"states/{entity_id}")
        except HassError:
            return None
        if not item:
            return None
        return State(item["entity_id"], item["state"], item.get("attributes") or {})

    # ------------------------------------------------------------ templates

    def template(self, source: str) -> str:
        """Render a Jinja template server-side. Handy for anything awkward over REST."""
        return str(self._request("POST", "template", json={"template": source}))

    # ------------------------------------------------------------- forecast

    def forecast(self, entity_id: str, kind: str = "hourly") -> list[dict[str, Any]]:
        payload = self._request(
            "POST",
            "services/weather/get_forecasts?return_response",
            json={"entity_id": entity_id, "type": kind},
        )
        response = (payload or {}).get("service_response") or {}
        entry = response.get(entity_id) or {}
        return entry.get("forecast") or []

    # ------------------------------------------------------------ calendars

    def calendar_events(
        self, entity_id: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        try:
            payload = self._request(
                "GET",
                f"calendars/{entity_id}",
                params={"start": start.isoformat(), "end": end.isoformat()},
            )
        except HassError as exc:
            log.warning("calendar %s unavailable: %s", entity_id, exc)
            return []
        return payload or []

    # -------------------------------------------------------------- history

    def seconds_in_state(
        self, entity_ids: list[str], target: str, since: datetime
    ) -> dict[str, float]:
        """Seconds each entity spent in `target` between `since` and now.

        Overlapping players are *not* deduplicated -- two Sonos speakers playing
        together count twice. The caller decides whether that is what it wants.
        """
        if not entity_ids:
            return {}

        payload = self._request(
            "GET",
            f"history/period/{since.isoformat()}",
            params={
                "filter_entity_id": ",".join(entity_ids),
                "minimal_response": "",
                "no_attributes": "",
            },
        )

        now = datetime.now(timezone.utc)
        totals: dict[str, float] = {entity: 0.0 for entity in entity_ids}

        for series in payload or []:
            if not series:
                continue
            entity_id = series[0].get("entity_id")
            if entity_id is None:
                continue
            for current, following in zip(series, series[1:] + [None]):
                if current.get("state") != target:
                    continue
                began = _parse_ts(current.get("last_changed") or current.get("last_updated"))
                ended = (
                    _parse_ts(following.get("last_changed") or following.get("last_updated"))
                    if following
                    else now
                )
                if began and ended and ended > began:
                    totals[entity_id] = totals.get(entity_id, 0.0) + (ended - began).total_seconds()

        return totals


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def window_start(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
