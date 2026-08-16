# Hallway Panel

Renders an 800×480 1-bit dashboard and serves it over HTTP for a
battery-powered e-paper display to fetch.

## Installing

This repository is the add-on. Copy it to `/addons/hallway-panel` on the Home
Assistant machine — the Samba share or SSH add-on will do — then:

**Settings → Add-ons → Add-on store → ⋮ → Check for updates**

It will appear under *Local add-ons*. Building takes a couple of minutes the
first time.

No access token is needed. `homeassistant_api` is enabled, so the Supervisor
hands the container a token and a route to Home Assistant on its own.

## Configuring

The options on this page are deployment settings only. Everything about *what
the panel shows* lives in a separate file, created on first start:

```
/addon_configs/hallway_panel/panel.yaml
```

Edit it with the File editor add-on and restart. Keeping it out of the image
means your settings survive rebuilding the add-on.

| Option | Meaning |
| --- | --- |
| `log_level` | `debug` while setting up, `info` afterwards. |
| `cache_seconds` | How long a render is reused before rebuilding it. Guards against a browser left open on the preview page polling Home Assistant continuously; the display polls far more slowly than this regardless. |

## Endpoints

Reachable at `http://<home-assistant>:8099`.

| Path | For |
| --- | --- |
| `/preview` | Open this in a browser. Shows the panel at full size and reloads every 30 seconds. |
| `/panel.png` | The image the display fetches. Honours `If-None-Match` and `If-Modified-Since`. |
| `/status` | ETag, size and seconds until the display should next wake, in about 70 bytes. |
| `/health` | Whether the last render used live data, and the reason if it did not. |

## What to expect on first run

Weather will be populated and most other blocks empty. That is not a fault —
those blocks collapse when they have nothing to say, and they need setting up on
the Home Assistant side first:

- **Calendar** — no Google Calendar is connected until you add the integration.
- **Commute** — needs Google Maps Travel Time sensors, one per route. Turn
  *off* automatic polling on each and drive updates from an automation inside
  the commute window; three routes at the default five-minute poll is roughly
  26,000 requests a month.
- **Bins** — the waste sensor may be reporting empty values. The log says so
  explicitly if it is.
- **Stats** — telly and music hours need `history_stats` sensors; steps need
  Health Connect enabling in the companion app on both phones.

Check `/health` first if the whole panel looks like the sample data — that means
Home Assistant could not be reached and it fell back to the fixture scene.
