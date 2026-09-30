"""The Music stat, from Spotify's own listening history.

`GET /me/player/recently-played` only ever retains a rolling buffer of roughly
the last 50 plays -- not just a page size, the backing store itself. `before`
and `after` are time cursors for navigating *within* that same bounded set, not
a way to page deeper into history. So there is no way to reconstruct "this
week" from a single query once someone has played more than a few dozen tracks
since Sunday.

The only sound approach is incremental: seed once from whatever the buffer
holds at connect time (`backfill`), then poll forward from a saved cursor on
every render cycle (`poll`), folding new plays into a persisted, pruned list
rather than ever re-deriving the week from Spotify directly.

A stat must never break the render, so every network call here is wrapped and
degrades to `NO_DATA` -- an unreachable account is exactly as fine as one that
was never connected.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from ..config import Config

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
RECENTLY_PLAYED_URL = "https://api.spotify.com/v1/me/player/recently-played"
SCOPE = "user-read-recently-played"

# Duplicated from stats.NO_DATA rather than imported -- stats imports this
# module to wire up the "spotify_hours" kind, and a shared one-character
# constant is not worth a cross-import cycle over.
NO_DATA = "—"

TIMEOUT = 15
# A week plus a day's margin, so a render right at the boundary still sees a
# full 7 days behind it.
PRUNE_AFTER_SECONDS = 8 * 86400


# ---------------------------------------------------------------------- auth


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """The one-time trade of an authorization code for a refresh_token."""
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    response = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(client_id, client_secret),
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


# ------------------------------------------------------------------- history


def _recently_played(
    access_token: str, *, after_ms: int | None = None, before_ms: int | None = None
) -> list[dict]:
    """One page (up to 50) of play history, newest first.

    `after_ms`/`before_ms` are Spotify's own cursor semantics: `after` asks for
    anything played since that instant (forward polling), `before` asks for
    anything played earlier than it (backward sweep at connect time). Passing
    both is meaningless to Spotify's API; callers never do.
    """
    params: dict[str, Any] = {"limit": 50}
    if after_ms is not None:
        params["after"] = after_ms
    if before_ms is not None:
        params["before"] = before_ms

    response = requests.get(
        RECENTLY_PLAYED_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get("items") or []


def backfill(access_token: str) -> list[dict]:
    """Everything currently in the recently-played buffer, swept backward.

    A single call might not even return a full page, and the buffer is bounded
    anyway -- so sweep with `before` until a page comes back empty, which is
    the only way to know the buffer is exhausted rather than just under-sized.
    """
    items: list[dict] = []
    before_ms: int | None = None
    seen_ts: set[str] = set()

    for _ in range(10):  # 10 * 50 is far past any plausible buffer size
        page = _recently_played(access_token, before_ms=before_ms)
        if not page:
            break

        new = [item for item in page if item.get("played_at") not in seen_ts]
        if not new:
            break
        items.extend(new)
        seen_ts.update(item["played_at"] for item in new)

        oldest = min(new, key=lambda item: item["played_at"])
        before_ms = _to_ms(oldest["played_at"])

    return items


# ------------------------------------------------------------------- storage


class SpotifyState:
    """The refresh_token and a pruned log of (played_at, duration) pairs."""

    def __init__(self, path: Path):
        self.path = path
        self.refresh_token: str | None = None
        self.cursor_ms: int | None = None
        self.plays: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.refresh_token = raw.get("refresh_token")
        self.cursor_ms = raw.get("cursor_ms")
        self.plays = raw.get("plays") or []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "refresh_token": self.refresh_token,
            "cursor_ms": self.cursor_ms,
            "plays": self.plays,
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def add_plays(self, items: list[dict]) -> None:
        now = time.time()
        for item in items:
            track = item.get("track") or {}
            self.plays.append(
                {
                    "ts": _to_ms(item["played_at"]) / 1000,
                    "seconds": (track.get("duration_ms") or 0) / 1000,
                }
            )
            self.cursor_ms = max(self.cursor_ms or 0, _to_ms(item["played_at"]))
        self.plays = [p for p in self.plays if now - p["ts"] < PRUNE_AFTER_SECONDS]

    def hours_this_week(self, *, days: int = 7) -> str:
        cutoff = time.time() - days * 86400
        total = sum(p["seconds"] for p in self.plays if p["ts"] >= cutoff)
        if not total:
            return NO_DATA
        minutes = round(total / 60)
        return f"{minutes // 60}h {minutes % 60:02d}m"


def _to_ms(played_at: str) -> int:
    """`played_at` is RFC 3339 UTC, e.g. "2026-09-29T18:03:11.123Z"."""
    cleaned = played_at.replace("Z", "+00:00")
    return int(datetime.fromisoformat(cleaned).timestamp() * 1000)


# ---------------------------------------------------------------------- poll


def state_path(config: Config, person: str) -> Path:
    """Each person connects their own Spotify account, so each gets their own
    state file -- derived from the single configured base path rather than a
    second config option, e.g. "/data/spotify.json" -> "/data/spotify_ed.json".
    """
    base = config.spotify_state_path
    return base.with_name(f"{base.stem}_{person}{base.suffix}")


def poll(config: Config, person: str) -> str:
    """The per-render, per-person entry point: refresh that person's token,
    pull anything new, and return their rolling week total. Never raises --
    any failure just means the stat reads NO_DATA until the next cycle, same
    as `_history_hours`.
    """
    client_id = config.spotify_client_id
    client_secret = config.spotify_client_secret
    if not (client_id and client_secret):
        return NO_DATA

    state = SpotifyState(state_path(config, person))
    if not state.refresh_token:
        return NO_DATA

    try:
        tokens = refresh_access_token(client_id, client_secret, state.refresh_token)
        access_token = tokens["access_token"]
        if tokens.get("refresh_token"):
            state.refresh_token = tokens["refresh_token"]

        items = _recently_played(access_token, after_ms=state.cursor_ms)
        state.add_plays(items)
        state.save()
    except Exception as exc:  # noqa: BLE001 - a stat must never break the render
        log.warning("spotify poll failed: %s", exc)
        return state.hours_this_week()

    return state.hours_this_week()
