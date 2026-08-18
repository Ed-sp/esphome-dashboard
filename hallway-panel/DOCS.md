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

Configuration lives in two places, split by what each is good at.

### On this page: deployment settings and secrets

| Option | Meaning |
| --- | --- |
| `log_level` | `debug` while setting up, `info` afterwards. |
| `cache_seconds` | How long a render is reused before rebuilding it. Guards against a browser left open on the preview polling Home Assistant continuously; the display polls far more slowly regardless. |
| `youversion_app_key` | Optional. Enables the verse of the day. |
| `esv_api_key` | Optional. Alternative verse provider. |

**Keys belong here, not in `panel.yaml`.** They are typed `password`, so Home
Assistant masks them in the interface, keeps them in the Supervisor's store
rather than a file on disk, and leaves them out of any YAML you might paste
somewhere while asking why something is broken. They reach the panel through the
environment and are never written to a file or a log line.

The three-dot menu on this card has **Edit in YAML** if you would rather type
these than fill in boxes.

### In `panel.yaml`: what the panel shows

Created on first start at:

```
/addon_configs/hallway_panel/panel.yaml
```

Edit it with the File editor add-on and restart. Keeping it out of the image
means your settings survive rebuilding the add-on.

Everything about content lives there — people and their calendars, commute rules
and thresholds, which bin is which, the four stat slots, which sky providers are
on, the refresh schedule. It stays a file rather than moving here because those
are nested lists, and this options schema handles flat scalars well and nested
lists-of-dictionaries badly. Forcing them in would make the interface worse than
the file it replaced.

## The live preview

**Hallway Panel appears in the sidebar.** That is the preview: the panel at
actual size, reloading every 30 seconds, so `panel.yaml` can be edited in one
tab and the result watched in another.

It runs through Ingress, so it is authenticated by Home Assistant and there is
no port to remember. Every link on the page is relative, which is what lets the
same page work both there and on the bare port.

## Endpoints

The display talks to `http://<home-assistant>:8099` directly — it cannot
authenticate against Ingress. Clearing the port in the add-on's Network settings
will stop the panel updating.

| Path | For |
| --- | --- |
| `/` and `/preview` | The preview page. Ingress lands on `/`. |
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
