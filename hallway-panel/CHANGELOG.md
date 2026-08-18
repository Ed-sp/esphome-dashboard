# Changelog

Home Assistant shows this when an update is available, so it says what changes
for you rather than what changed in the code.

## 0.2.0

**The panel now fits a 7.5" V1 (640×384) as well as the V2 (800×480).** Set the
size in `panel.yaml`; an unlisted one fails at startup naming the sizes that
exist. The two layouts are tuned separately rather than scaled — 1-bit type does
not survive being multiplied by 0.8 — so the smaller panel keeps the full
seven-day forecast and gives up one calendar event, one stat and one alert.

**The preview is in the sidebar.** It runs through Ingress, so it is
authenticated and there is no port to remember. The mapped port stays, because
the display cannot authenticate against Ingress and needs it.

**Verse of the day.** On the days with no collect, the block shows a verse
instead of cycling the bundled psalms. Provide a key below to enable it;
YouVersion also needs a licence accepted per version in their dashboard, or it
returns 403 for everything including public-domain versions.

**API keys are options on the Configuration page**, typed `password`. Before
this there was no way to give the add-on a key at all.

**A fallback screen** for when Home Assistant cannot be reached and the last
good render is too old to trust. It says so plainly rather than showing stale
weather, which was the previous behaviour and could have sent someone out
dressed for the wrong day.

Also: bin collections read from the waste calendar rather than the sensor, and
no longer confuse "Non-recyclable refuse waste" with recycling; plant watering
can read a threshold helper so the panel and your phone agree; eclipses say what
the UK actually gets rather than the headline; and the electricity stat reads a
weekly utility meter.

## 0.1.0

First working version. Renders the panel from Home Assistant and serves it over
HTTP for an ESP32 to fetch.
