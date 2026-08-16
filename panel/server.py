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
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, request

from . import build as builder
from . import sample
from .config import Config, ConfigError, load
from .hass import Hass, HassError
from .render import layout

log = logging.getLogger(__name__)

CACHE_SECONDS = int(os.environ.get("PANEL_CACHE_SECONDS", "45"))


class Renderer:
    """Caches the most recent successful render and its ETag."""

    def __init__(self, config: Config):
        self.config = config
        self._png: bytes | None = None
        self._etag: str | None = None
        self._rendered_at: float = 0.0
        self._error: str | None = None

    @property
    def stale(self) -> bool:
        return self._png is None or (time.monotonic() - self._rendered_at) > CACHE_SECONDS

    def render(self, *, force: bool = False) -> tuple[bytes, str]:
        if not force and not self.stale and self._png and self._etag:
            return self._png, self._etag

        try:
            hass = Hass(self.config.base_url, self.config.token)
            panel = builder.build(self.config, hass)
            self._error = None
        except (HassError, ConfigError) as exc:
            log.error("live render failed: %s", exc)
            self._error = str(exc)
            if self._png and self._etag:
                # Keep serving the last good image rather than going blank.
                return self._png, self._etag
            panel = sample.panel()

        png = layout.render(panel).to_png_bytes()
        etag = hashlib.sha256(png).hexdigest()[:16]

        self._png, self._etag, self._rendered_at = png, etag, time.monotonic()
        return png, etag

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self._rendered_at if self._png else -1.0


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
        wake_at = datetime.strptime(refresh.get("wake_after_sleep", "05:45"), "%H:%M").time()
        target = now.replace(hour=wake_at.hour, minute=wake_at.minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max(300, int((target - now).total_seconds()))

    if not anyone_home:
        return refresh.get("away_minutes", 60) * 60

    window = refresh.get("commute_window", ["06:00", "09:00"])
    start = datetime.strptime(window[0], "%H:%M").time()
    end = datetime.strptime(window[1], "%H:%M").time()
    if start <= now.time() < end and now.weekday() < 5:
        return refresh.get("commute_minutes", 10) * 60

    return refresh.get("awake_minutes", 20) * 60


def create_app(config: Config | None = None) -> Flask:
    config = config or load()
    app = Flask(__name__)
    renderer = Renderer(config)

    @app.get("/panel.png")
    def panel_png() -> Response:
        png, etag = renderer.render(force=request.args.get("force") is not None)
        if request.headers.get("If-None-Match") == etag:
            # Nothing changed: the device skips the display refresh entirely,
            # which is worth roughly a third of the wake and saves ghosting.
            return Response(status=304, headers={"ETag": etag})
        return Response(
            png,
            mimetype="image/png",
            headers={"ETag": etag, "Cache-Control": "no-cache", "Content-Length": str(len(png))},
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
        return jsonify(
            {
                "ok": renderer.error is None,
                "error": renderer.error,
                "render_age_seconds": round(renderer.age_seconds, 1),
                "cache_seconds": CACHE_SECONDS,
            }
        )

    @app.get("/preview")
    def preview() -> Response:
        _, etag = renderer.render()
        banner = (
            f'<p class="err">Live data unavailable, showing the fixture scene: {renderer.error}</p>'
            if renderer.error
            else ""
        )
        return Response(_PREVIEW.format(etag=etag, banner=banner), mimetype="text/html")

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
  img {{ display:block; image-rendering:pixelated; background:#fff }}
  .err {{ background:#5b2222; border-left:3px solid #e08a54; padding:10px 14px; border-radius:3px }}
  a {{ color:#8fb0ff }}
</style>
<h1>Hallway panel &middot; 800 &times; 480 &middot; 1-bit</h1>
{banner}
<div class="bezel"><img src="/panel.png?v={etag}" width="800" height="480" alt="panel"></div>
<p>Reloads every 30s &middot; <a href="/panel.png?force=1">force a re-render</a> &middot;
   <a href="/health">health</a></p>
"""
