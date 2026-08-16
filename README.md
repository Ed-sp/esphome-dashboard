# Hallway panel

A battery-powered 7.5″ monochrome e-paper dashboard for the hallway, driven by
Home Assistant. Home Assistant renders an 800×480 1-bit PNG; an ESP32 wakes,
fetches it, pushes it to the panel, and goes back to sleep.

![The panel](docs/panel-busy.png)

## Why a PNG and not ESPHome lambdas

Drawing on the device is the more usual approach and it very nearly won. What
decided it:

* **Glyph lists.** ESPHome fonts need every character declared up front, and
  anything undeclared renders as a black box. Calendar titles are arbitrary
  text — curly apostrophes, em-dashes, accents — so that would be a permanent
  maintenance tax.
* **Reflow.** The collect is wrapped serif, the alert list varies in length, and
  the commute block disappears entirely after 09:00. Vertical reflow in lambdas
  is unpleasant.
* **The graph.** Per-hour dither density clipped under a temperature curve is a
  few lines with Pillow and a slog otherwise.

The cost is a service to host and a blank panel if it dies, which the ESP
mitigates by caching the last good image and falling back to a stored card.

## Design rules

The panel is 1-bit. There is no grey, which drives three constraints:

1. **Hierarchy comes from size and weight, never colour.** A secondary value is
   a smaller, lighter value beside a bigger one.
2. **Solid black is an alarm, not decoration.** Exactly one element fills black —
   the bin alert, on the two evenings a fortnight it matters. Everything else is
   outlined, so the dark bar reads from the end of the hall without being read.
3. **Dither is the only tint.** Ordered 4×4 tiles at 6/12/25/50% give four
   shading steps for the rain fill. Anything needing a fifth wants a different
   chart.

Blocks collapse rather than draw empty headings, so a dull Sunday looks like
this — no "Leaving", no "Needs you", no shading under the graph:

![A quiet day](docs/panel-quiet.png)

## Layout

Left column is *today, act now*. Right column is *ahead, plan around*. The bottom
band closes with the collect and the week's numbers.

## Running it

Offline, against the fixtures — no Home Assistant needed:

```bash
pip install -r requirements.txt
python render_panel.py --sample                      # busy weekday morning
python render_panel.py --sample --scene quiet        # dull Sunday
python tools/icon_sheet.py                           # icon contact sheet
```

Against live data:

```bash
python serve.py
```

Then open <http://127.0.0.1:8099/preview>, which reloads every 30 seconds. Set
`HA_TOKEN` to a long-lived access token first (Profile → Security in Home
Assistant); without one the service logs why and serves the fixture scene, so
the preview still works.

| Route | For |
| --- | --- |
| `/panel.png` | The device. Honours both `If-None-Match` and `If-Modified-Since`. |
| `/status` | ETag, byte count and seconds-to-next-wake in ~70 bytes. |
| `/preview` | A browser, for iterating on the layout. |
| `/next-wake` | Just the sleep interval, if you only want that. |
| `/health` | Whether the last render used live data, and why not if it didn't. |

### Why two conditional forms, and what they are actually worth

ESPHome's `online_image` already sends `If-None-Match` on its own and skips the
download on a 304 — so on a mains-powered device this needs nothing from us. But
it holds the ETag in a plain member (`online_image.h:98`) and deep sleep wipes
RAM, so a battery panel starts every wake with no ETag and downloads the whole
image regardless. There is no setter, and `set_url()` explicitly clears it.

`If-Modified-Since` is the way round that: the device can persist *its own*
timestamp across deep sleep, with nothing to read back out of the component.
`Last-Modified` tracks when the content last **changed**, not when it was last
rendered — re-rendering identical pixels deliberately leaves it alone, or the
header would never match twice.

Worth being honest about the size of the prize. Per wake, roughly:

| | duration | current | share |
| --- | --- | --- | --- |
| WiFi association | 2–5 s | ~120 mA | **~85%** |
| Display refresh | ~2 s | ~25 mA | ~10% |
| Downloading 7 KB | ~0.1 s | ~120 mA | ~2% |

Skipping the download saves almost nothing; the association dominates and
happens either way. What conditional requests really buy is **not refreshing the
display when nothing changed** — no ghosting, and no 7.5" panel flashing black
and white in a hallway for no reason. The battery lever is wake frequency, not
bytes.

`/status` exists because the device needs the sleep interval anyway: one request
answers both questions, so an unchanged wake is a single ~70-byte round trip
instead of two.

## Configuration

Everything switchable lives in [`config.yaml`](config.yaml) — Ed's workplace,
commute rules and thresholds, which bin is which, the four stat slots, and the
refresh schedule. Hannah's workplace is fixed today but uses the same shape as
Ed's so it can gain options without a code change.

The Home Assistant token is read from the environment (`HA_TOKEN` by default) and
is never written to the config.

## Layout of the code

| Path | What it does |
| --- | --- |
| `panel/model.py` | What the layout draws. No Home Assistant concepts — everything is already resolved and formatted, so the rule engine is testable without a display. |
| `panel/sample.py` | Two fixture scenes: a busy weekday morning and a quiet Sunday. |
| `panel/render/canvas.py` | 1-bit drawing surface: ordered dithering, tracked text, word wrap, dashed and half-tone rules. |
| `panel/render/icons.py` | Twenty icons as Pillow primitives, plus HA weather-state mapping. Not a font, so there is no TTF to ship and no glyph list to maintain. |
| `panel/render/fonts.py` | Font resolution with Windows and Debian fallbacks. |
| `panel/render/layout.py` | The 800×480 composition. Coordinates match the approved design. |
| `panel/config.py` | Loads `config.yaml`, and fails loudly on the few mistakes that would otherwise render a silently wrong panel. |
| `panel/hass.py` | The five REST calls the panel needs. Knows nothing about panels. |
| `panel/sources/` | One module per region, each returning finished model objects. |
| `panel/build.py` | Assembles a `Panel` from one state snapshot. Each section is guarded separately. |
| `panel/server.py` | Flask app, render cache, ETag, and the wake-interval calculation. |

### One gotcha worth knowing

Mode `"1"` images make PIL select FreeType's monochrome rasteriser, which rounds
every glyph advance up to a whole pixel. `getlength()` defaults to antialiased
metrics and under-reports by roughly 50px across a line of body text. Every
measurement in `canvas.py` passes `mode="1"` explicitly. If text starts
overrunning its column, that is the first thing to check.

## The collect

`panel/liturgy.py` computes the church calendar rather than tabulating it:
Easter drives the movable feasts, Advent Sunday follows from Christmas Day, and
everything else falls out of those two. Nothing needs updating year to year.

Because a Sunday's collect carries through the following weekdays, `key_for`
resolves any date back to the day governing it — a principal feast if the date
is one, otherwise the most recent Sunday. That turns 365 entries into 63.

[`data/collects.yaml`](data/collects.yaml) holds the BCP 1662 collects in
traditional wording. Common Worship texts are in copyright and are not included.
**The entries were written from memory and should be checked against a printed
copy** — the wording of a collect matters.

Any key with no entry falls back to [`data/fallbacks.yaml`](data/fallbacks.yaml),
a short psalm or Pauline prayer picked by date so it is stable through the day
and rotates across days. That is the intended behaviour, not a gap to be filled
in a hurry with something approximate.

```bash
python tools/liturgy_year.py            # every key this year, and its date
python tools/liturgy_year.py --missing  # just the gaps
python tools/liturgy_year.py 2027       # any year
```

Collects vary from one sentence to a full paragraph, so the layout picks a type
size that fits rather than clipping a prayer mid-line: it tries 13px over three
lines first and steps down to 10px over five, choosing the first that holds the
whole text.

## The sky line

One line under the calendar, when there is something worth going outside for.
On 218 days of 2026 there is nothing and the line does not appear at all, which
is the intended behaviour.

Events come from independent **providers** that compete for that one line, the
highest-ranked winning. Each gets a block in `config.yaml` and can be switched
off without touching code:

```yaml
sky:
  events:
    showers: { enabled: true, min_zhr: 50 }   # just the big three
    moon:    { enabled: false }               # stop it filling 75 days a year
```

Adding one means writing a function in `panel/sources/sky/`, decorating it with
`@provider("name")`, and importing it in that package's `__init__`. Nothing else
needs to know it exists.

Two properties are worth preserving if you edit that package. **A provider that
raises loses only itself** — a panel that rendered nothing because a satellite
API changed its JSON would be a bad trade. And **rank is comparable across
providers**, since they are competing for one line; the shared scale lives in
`sky.RANKS`.

```bash
python tools/sky_year.py 2026            # what the line says across a year
python tools/sky_year.py --off moon      # as if that provider were disabled
```

Meteor showers and eclipses come from [`data/sky.yaml`](data/sky.yaml). Shower
peaks land within a day of the same date each year and eclipse dates are known
centuries ahead, so fetching them would add a network dependency and a failure
mode in exchange for nothing. Eclipse entries were checked against
timeanddate.com and the Royal Observatory rather than written from memory, and
the notes say what the UK actually gets — the August 2027 "total" is a partial
here, about a third covered.

Moon phases are computed, using Meeus chapter 49. The tempting shortcut — mean
synodic month counted from a known new moon — is wrong by up to fourteen hours
because the Moon's orbit is eccentric, which names the wrong day often enough to
matter. The periodic terms bring it inside a few minutes.

That calculation validates itself rather neatly: solar eclipses only occur at
new moon and lunar eclipses only at full moon, so the verified eclipse dates
double as test vectors. All seven land on the computed day, and the 28 August
2026 full moon computes to 05:19 BST against a published greatest eclipse of
05:12.

### Aurora

The one thing here that has to be fetched, because it is about tonight rather
than about orbital mechanics. [AuroraWatch UK](https://aurorawatch.lancs.ac.uk/)
run magnetometers in the UK and publish a four-level alert calibrated to *British*
latitudes — which is why this beats reading a raw Kp index, since Kp 6 means
something very different in Shetland than in Oxfordshire.

Their XML API is used rather than the RSS feed: versioned, documented, and it
returns a machine-readable `status_id` instead of a headline to regex. Two
obligations come with it, both honoured in `aurora.py` — poll no faster than
every three minutes (the default here is fifteen), and send a descriptive
User-Agent. Their docs also ask that the published thresholds are not adjusted,
so the code maps levels to wording without inventing intermediate states; what
`config.yaml` controls is which level is worth interrupting the panel for.

A red alert outranks every fixed event, including a total lunar eclipse. An
eclipse is predictable a decade out and you can plan around it; an aurora
visible from Oxfordshire is rare and happening now.

If the fetch fails the last reading is kept rather than cleared. A stale green
is harmless, and a stale red for one refresh is better than dropping an alert
because the wifi hiccuped.

Adding another live feed — ISS passes, say — means returning a `SkyEvent` and
appending it in `build._sky_line`.

## Still to build
* **Add-on packaging.** Dockerfile and manifest.
* **ESPHome firmware.** Wake, fetch, compare ETag, draw or skip, read
  `/next-wake`, sleep.

Blocked on Home Assistant configuration rather than on code:

* **Google Calendar** is not connected, so the agenda is empty.
* **Google Maps Travel Time** sensors do not exist, so the commute block stays
  collapsed. Turn off automatic polling and drive updates from an automation
  inside the commute window — three routes at the default 5-minute poll is about
  26,000 requests a month.
* **The waste sensor** runs but reports empty strings for every bin, so the
  alert can never fire. `alerts.py` logs a warning saying exactly this.
* **Health Connect** sensors are not enabled, so the steps stat shows a dash.
