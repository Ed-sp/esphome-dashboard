"""HTTP service the ESP32 and the browser both talk to.

    GET /panel.png    the panel, with an ETag so an unchanged render costs the
                      device a 304 and no display refresh
    GET /preview      a browser page that reloads itself, for iterating on the
                      layout against live data
    GET /next-wake    seconds until the device should wake again
    GET /health       plain JSON, for a container healthcheck

Renders are cached briefly so that a browser left open on /preview -- or a device
retrying -- does not hammer Home Assistant.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, request
from PIL import Image, ImageOps

from . import build as builder
from .config import Config, ConfigError, load
from .hass import Hass, HassError
from .render import fallback, layout
from .sources import spotify

log = logging.getLogger(__name__)

CACHE_SECONDS = int(os.environ.get("PANEL_CACHE_SECONDS", "45"))


class Renderer:
    """Caches the most recent successful render, its ETag, and when it changed."""

    def __init__(self, config: Config):
        self.config = config
        self._png: bytes | None = None
        self._etag: str | None = None
        self._rendered_at: float = 0.0
        self._error: str | None = None
        # Wall-clock time the *content* last changed, which is not the same as
        # when it was last rendered: re-rendering identical pixels must not move
        # this, or If-Modified-Since would never match.
        self._changed_at: datetime = datetime.now(timezone.utc)
        # When Home Assistant was last actually reached. None until it has been.
        self._last_success: datetime | None = None
        self.stale_after = int(
            config.raw.get("refresh", {}).get("trust_last_render_hours", 6) * 3600
        )

    def _outage_age(self) -> float | None:
        """Seconds since the last successful render, or None if there never was one."""
        if self._last_success is None:
            return None
        return (datetime.now(timezone.utc) - self._last_success).total_seconds()

    @property
    def stale(self) -> bool:
        return self._png is None or (time.monotonic() - self._rendered_at) > CACHE_SECONDS

    def render(self, *, force: bool = False, invert: bool = False) -> tuple[bytes, str]:
        """Return (png, etag). `invert` is applied on top of the cached render,
        not baked into it -- otherwise a cache hit would hand back whatever
        invert setting happened to be requested when the cache was last filled,
        which is why this used to only take effect together with `force`.
        """
        if not force and not self.stale and self._png and self._etag:
            return self._served(invert)

        try:
            hass = Hass(self.config.base_url, self.config.token)
            panel = builder.build(self.config, hass)
            self._error = None
            self._last_success = datetime.now(timezone.utc)
        except (HassError, ConfigError) as exc:
            log.error("live render failed: %s", exc)
            self._error = str(exc)

            age = self._outage_age()
            if self._png and self._etag and age is not None and age < self.stale_after:
                # A forecast an hour old is still roughly right, and a panel that
                # blanks at the first dropped packet is worse than a slightly
                # stale one. Keep showing the last good image.
                log.info("serving the last good render, %.0f min old", age / 60)
                return self._png, self._etag

            # Past that, the image should not be trusted. Deliberately NOT the
            # fixture scene: invented weather that looks real would send someone
            # out of the door dressed for the wrong day.
            log.warning("no trustworthy render available; showing the fallback screen")
            panel = None

        if panel is None:
            canvas = fallback.render(
                geometry=self.config.geometry,
                reason=self._error,
                last_good=self._last_success.astimezone(ZoneInfo(self.config.timezone))
                if self._last_success
                else None,
            )
        else:
            canvas = layout.render(panel, self.config.geometry)

        png = canvas.to_png_bytes()
        etag = hashlib.sha256(png).hexdigest()[:16]

        if etag != self._etag:
            self._changed_at = datetime.now(timezone.utc)

        self._png, self._etag, self._rendered_at = png, etag, time.monotonic()
        return self._served(invert)

    def _served(self, invert: bool) -> tuple[bytes, str]:
        """The cached render, inverted on the way out if asked -- so an
        `invert` request always matches what is actually served, cache hit or
        not, rather than only on the request that happened to (re)render.
        """
        if not invert:
            return self._png, self._etag
        return _invert_png(self._png), f"{self._etag}-inv"

    @property
    def changed_at(self) -> datetime:
        return self._changed_at

    @property
    def showing_fallback(self) -> bool:
        if self._error is None:
            return False
        age = self._outage_age()
        return age is None or age >= self.stale_after

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self._rendered_at if self._png else -1.0


def _invert_png(png: bytes) -> bytes:
    image = ImageOps.invert(Image.open(BytesIO(png)))
    out = BytesIO()
    image.save(out, format="PNG", optimize=True, bits=1)
    return out.getvalue()


def http_date(when: datetime) -> str:
    """RFC 7231 date, which is always English and always GMT regardless of locale."""
    return format_datetime(when, usegmt=True)


def _not_modified_since(header: str, changed_at: datetime) -> bool:
    try:
        since = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return False
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    # HTTP dates have one-second resolution, so a change in the same second as
    # the client's timestamp would be missed by a strict comparison.
    return changed_at.replace(microsecond=0) <= since


def _next_change_cap(config: Config, now: datetime, seconds: int) -> int:
    """Shrink a sleep so it never runs past a moment the panel's content can
    flip -- right now, that's just the waste alert's show/hide times.

    Without this, a device on a 20-60 minute cycle can sleep straight through
    18:00 and keep showing yesterday's (empty) panel for most of an hour after
    the bin reminder was supposed to appear. Waking a little early when
    nothing was actually due that day is harmless; the missed reminder is not.
    """
    if not config.waste.get("calendar"):
        return seconds

    try:
        show_from = datetime.strptime(config.waste["show_from"], "%H:%M").time()
        hide_at = datetime.strptime(config.waste["hide_at"], "%H:%M").time()
    except (KeyError, ValueError):
        return seconds

    def next_occurrence(at) -> datetime:
        candidate = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    boundary = min(next_occurrence(show_from), next_occurrence(hide_at))
    until_boundary = (boundary - now).total_seconds()
    if until_boundary >= seconds:
        return seconds

    # Land just past the boundary rather than on it, so the >= / < comparisons
    # in alerts.waste() have already tipped by the time this wake renders.
    return max(60, int(until_boundary) + 30)


def next_wake_seconds(config: Config) -> int:
    """How long the device should sleep, from presence and the sleep schedule."""
    refresh = config.refresh
    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)

    try:
        hass = Hass(config.base_url, config.token)
        states = hass.states()
    except (HassError, ConfigError):
        return refresh.get("awake_minutes", 20) * 60

    def state_of(entity_id: str | None) -> str | None:
        entry = states.get(entity_id) if entity_id else None
        return entry.state if entry else None

    asleep = state_of(refresh.get("asleep_entity")) == "on"
    anyone_home = any(state_of(person.person) == "home" for person in config.people)

    if asleep:
        # Asleep is the one case that does not get capped: a bin reminder is
        # not worth waking someone in the night for, so this rides through to
        # the normal wake_after_sleep time regardless.
        wake_at = datetime.strptime(refresh.get("wake_after_sleep", "05:45"), "%H:%M").time()
        target = now.replace(hour=wake_at.hour, minute=wake_at.minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max(300, int((target - now).total_seconds()))

    if not anyone_home:
        return _next_change_cap(config, now, refresh.get("away_minutes", 60) * 60)

    window = refresh.get("commute_window", ["06:00", "09:00"])
    start = datetime.strptime(window[0], "%H:%M").time()
    end = datetime.strptime(window[1], "%H:%M").time()
    if start <= now.time() < end and now.weekday() < 5:
        return _next_change_cap(config, now, refresh.get("commute_minutes", 10) * 60)

    return _next_change_cap(config, now, refresh.get("awake_minutes", 20) * 60)


def _spotify_links(config: Config) -> str:
    """One line per person: a login link, or a connected check mark.

    Lets you start the one-time consent from the preview page rather than
    hand-typing /spotify/login?person=<key> -- opens in a new tab so the
    auto-refreshing preview underneath keeps running.
    """
    if not (config.spotify_client_id and config.spotify_redirect_uri):
        return ""

    rows = []
    for person in config.people:
        connected = bool(spotify.SpotifyState(spotify.state_path(config, person.key)).refresh_token)
        if connected:
            rows.append(f"{person.name}: connected")
        else:
            rows.append(
                f'<a href="spotify/login?person={person.key}" target="_blank">'
                f"Connect {person.name}'s Spotify</a>"
            )
    return "<p>" + " &middot; ".join(rows) + "</p>" if rows else ""


def create_app(config: Config | None = None) -> Flask:
    config = config or load()
    app = Flask(__name__)
    renderer = Renderer(config)

    @app.get("/panel.png")
    def panel_png() -> Response:
        png, etag = renderer.render(
            force=request.args.get("force") is not None,
            invert=request.args.get("invert") is not None
        )
        last_modified = http_date(renderer.changed_at)

        # Both conditional forms are honoured, because the two ways of driving
        # this device need different ones.
        #
        # ESPHome's online_image sends If-None-Match by itself and skips the
        # download on a 304 -- but it keeps the ETag in RAM, and deep sleep
        # wipes RAM, so a battery panel starts every wake with no ETag. The
        # device can persist its own timestamp across sleep, though, which is
        # why If-Modified-Since is supported as well: it needs no value read
        # back out of the component.
        #
        # The saving is smaller than it looks. Skipping a 7 KB download is
        # perhaps 2% of a wake; the WiFi association dominates and happens
        # regardless. What this really buys is not refreshing the display when
        # nothing changed, which avoids ghosting and stops the panel flashing
        # black and white in a hallway for no reason.
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304, headers={"ETag": etag, "Last-Modified": last_modified})

        since = request.headers.get("If-Modified-Since")
        if since and _not_modified_since(since, renderer.changed_at):
            return Response(status=304, headers={"ETag": etag, "Last-Modified": last_modified})

        return Response(
            png,
            mimetype="image/png",
            headers={
                "ETag": etag,
                "Last-Modified": last_modified,
                "Cache-Control": "no-cache",
                "Content-Length": str(len(png)),
            },
        )

    @app.get("/status")
    def status() -> Response:
        """What the device asks before deciding whether to download anything.

        One request answers both questions it has -- has the picture changed,
        and how long should I sleep -- because a sleeping ESP32 cannot be pushed
        to and every extra round trip is radio time on a battery.

        The response is a couple of hundred bytes against a ~7 KB PNG, so on a
        wake where nothing changed the device skips the download *and* the
        display refresh.
        """
        png, etag = renderer.render()
        return jsonify(
            {
                "etag": etag,
                "bytes": len(png),
                "next_wake": next_wake_seconds(config),
                "live": renderer.error is None,
            }
        )

    @app.get("/next-wake")
    def next_wake() -> Response:
        return jsonify({"seconds": next_wake_seconds(config)})

    @app.get("/health")
    def health() -> Response:
        outage = renderer._outage_age()
        return jsonify(
            {
                "ok": renderer.error is None,
                "error": renderer.error,
                "render_age_seconds": round(renderer.age_seconds, 1),
                "seconds_since_home_assistant": round(outage, 1) if outage else outage,
                "showing_fallback": renderer.showing_fallback,
                "cache_seconds": CACHE_SECONDS,
            }
        )

    @app.get("/preview")
    def preview() -> Response:
        _, etag = renderer.render()
        geometry = config.geometry

        if renderer.error and renderer.showing_fallback:
            note = f"Home Assistant unreachable, showing the fallback screen: {renderer.error}"
        elif renderer.error:
            note = f"Home Assistant unreachable, showing the last good render: {renderer.error}"
        else:
            note = ""

        return Response(
            _PREVIEW.format(
                etag=etag,
                width=geometry.width,
                height=geometry.height,
                size=geometry.name,
                banner=f'<p class="err">{note}</p>' if note else "",
                spotify_links=_spotify_links(config),
            ),
            mimetype="text/html",
        )

    # Ingress lands on the container root, so that is where the preview has to
    # be. Every link and image below it is relative, which is what lets the same
    # page work both through Home Assistant's ingress path and on the bare port
    # the ESP32 uses.
    app.add_url_rule("/", "root", preview)

    # The one-time Spotify consent round trip. Both routes trust whoever can
    # reach them exactly as much as every other route here (ingress or the
    # user's own HTTPS, no separate login) -- this is a single-user hobby
    # panel, not a multi-tenant service, so a module-level CSRF token is
    # proportionate rather than a real session store.
    _pending_state: dict[str, str] = {}

    @app.get("/spotify/login")
    def spotify_login() -> Response:
        person = request.args.get("person")
        valid = {p.key for p in config.people}
        if not person or person not in valid:
            return Response(
                f"Pass ?person=<key>, one of: {', '.join(sorted(valid))}. "
                "Each person connects their own Spotify account separately.",
                status=400,
            )
        if not (config.spotify_client_id and config.spotify_redirect_uri):
            return Response(
                "Set spotify_client_id, spotify_client_secret and "
                "spotify_redirect_uri in the add-on's options first.",
                status=400,
            )
        state = secrets.token_urlsafe(16)
        _pending_state["state"] = state
        _pending_state["person"] = person
        url = spotify.authorize_url(
            config.spotify_client_id, config.spotify_redirect_uri, state
        )
        return Response(status=302, headers={"Location": url})

    @app.get("/spotify/callback")
    def spotify_callback() -> Response:
        error = request.args.get("error")
        if error:
            return Response(f"Spotify declined: {error}", status=400)

        code = request.args.get("code")
        state = request.args.get("state")
        if not code or not state or state != _pending_state.get("state"):
            return Response("Missing or mismatched state -- start again at /spotify/login.", status=400)
        person = _pending_state.pop("person", None)
        _pending_state.pop("state", None)
        if not person:
            return Response("Lost track of which person this was -- start again at /spotify/login.", status=400)

        try:
            tokens = spotify.exchange_code(
                config.spotify_client_id,
                config.spotify_client_secret,
                code,
                config.spotify_redirect_uri,
            )
            spotify_state = spotify.SpotifyState(spotify.state_path(config, person))
            spotify_state.refresh_token = tokens["refresh_token"]
            spotify_state.add_plays(spotify.backfill(tokens["access_token"]))
            spotify_state.save()
        except Exception as exc:  # noqa: BLE001 - report it, don't 500 on a bad hop
            log.error("spotify callback failed: %s", exc)
            return Response(f"Spotify connection failed: {exc}", status=500)

        return Response(f"Spotify connected for {person} -- you can close this tab.")

    return app


_PREVIEW = """<!doctype html><meta charset="utf-8">
<title>Hallway panel preview</title>
<meta http-equiv="refresh" content="30">
<style>
  body {{ background:#2a2c2f; color:#e8e8e4; font:14px/1.5 system-ui, sans-serif;
         margin:0; padding:28px; display:flex; flex-direction:column; align-items:center; gap:18px }}
  h1 {{ font-size:15px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
        color:#9aa0a6; margin:0 }}
  .bezel {{ background:#c9cac4; padding:12px; border-radius:5px;
            box-shadow:0 10px 30px rgba(0,0,0,.45) }}
  img {{ display:block; image-rendering:pixelated; background:#fff; max-width:100% }}
  .err {{ background:#5b2222; border-left:3px solid #e08a54; padding:10px 14px;
          border-radius:3px; max-width:60em }}
  a {{ color:#8fb0ff }}
</style>
<h1>Hallway panel &middot; {size} &middot; 1-bit</h1>
{banner}
<div class="bezel"><img src="panel.png?v={etag}" width="{width}" height="{height}" alt="panel"></div>
<p>Reloads every 30s &middot; <a href="panel.png?force=1">force a re-render</a> &middot;
   <a href="health">health</a> &middot; <a href="status">status</a></p>
{spotify_links}
"""
