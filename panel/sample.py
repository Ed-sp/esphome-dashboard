"""The exact scene from the approved mockup, as data.

Used by `render_panel.py --sample` so the layout can be worked on without a live
Home Assistant, and as the fixture for layout regression checks.
"""

from __future__ import annotations

from .model import Alert, Collect, Commute, Day, Event, Hour, Now, Panel, Stat

_TEMPS = [16, 17, 18, 19, 20, 21, 22, 23, 23, 22, 21, 19, 18, 17, 16, 15, 15, 14, 14, 13, 13, 14, 16, 18]
_RAIN = [10, 10, 5, 5, 0, 0, 0, 10, 20, 40, 70, 80, 60, 30, 20, 10, 10, 5, 5, 0, 0, 0, 5, 10]
_START_HOUR = 8


def panel() -> Panel:
    hours = [
        Hour(
            hour=(_START_HOUR + i) % 24,
            temperature=temp,
            rain=rain,
            night=not (6 <= (_START_HOUR + i) % 24 < 21),
        )
        for i, (temp, rain) in enumerate(zip(_TEMPS, _RAIN))
    ]

    return Panel(
        date_label="Thursday 13 August",
        now=Now(
            temperature=17,
            condition="partlycloudy",
            summary="Partly cloudy",
            feels_like=15,
            sunset="20:31",
        ),
        week=[
            Day("Today", "partlycloudy", 23, 13, 30),
            Day("Fri", "rainy", 21, 14, 60),
            Day("Sat", "cloudy", 19, 13, 20),
            Day("Sun", "partlycloudy", 22, 15, 10),
            Day("Mon", "sunny", 24, 16, 0),
            Day("Tue", "partlycloudy", 21, 14, 40),
            Day("Wed", "rainy", 18, 12, 70),
        ],
        hours=hours,
        rain_summary="13–23°  ·  RAIN 80% AT 18:00",
        commutes=[
            Commute("Ed", "Yarnton", "bike", 24, delta_minutes=7, note="dry until 09:00"),
            Commute("Hannah", "Oxford", "car", 38, note="as usual"),
        ],
        alerts=[
            Alert("Green bin out tonight", icon="recycle", urgent=True),
            Alert("Monstera needs water in 2 days", icon="leaf"),
            Alert("Front door sensor battery at 12%", icon="battery"),
        ],
        events=[
            Event("E", "Tonight 19:30", "Bell ringing practice"),
            Event("H", "Fri 09:00", "Dentist — Botley Road"),
            Event("H", "Sat 11:00", "Alice's birthday, Witney"),
            Event("E", "Sun 14:00", "Cycling with Tom — Wytham"),
        ],
        sky="Perseids peak tonight, after 23:00",
        stats=[
            Stat("Telly", "9h 20m"),
            Stat("Music", "6h 12m"),
            Stat("Steps · Ed / Hannah", "58k / 71k"),
            Stat("Electricity", "84 kWh"),
        ],
        collect=Collect(
            title="Collect · Trinity 10",
            text=(
                "Let your merciful ears, O Lord, be open to the prayers of your humble "
                "servants; and that they may obtain their petitions make them to ask such "
                "things as shall please you; through Jesus Christ our Lord."
            ),
        ),
    )


def quiet() -> Panel:
    """A Sunday afternoon: nobody commuting, nothing overdue, no rain.

    The point of this fixture is to prove the panel goes quiet rather than
    drawing empty headings -- no "Leaving" block, no "Needs you" block, and a
    graph with no shading under it at all.
    """
    base = panel()
    temps = [19, 20, 21, 22, 22, 21, 20, 19, 18, 17, 16, 16, 15, 15, 14, 14, 14, 15, 16, 18, 20, 21, 22, 22]
    base.date_label = "Sunday 16 August"
    base.now = Now(temperature=22, condition="sunny", summary="Sunny", feels_like=23, sunset="20:24")
    base.hours = [
        Hour(hour=(13 + i) % 24, temperature=t, rain=0, night=not (6 <= (13 + i) % 24 < 21))
        for i, t in enumerate(temps)
    ]
    base.rain_summary = "14–22°  ·  DRY ALL DAY"
    base.commutes = []
    base.alerts = []
    base.events = [
        Event("H", "Mon 09:00", "Dentist — Botley Road"),
        Event("E", "Tue 19:30", "Bell ringing practice"),
        Event("E", "Thu 18:00", "Bins out"),
    ]
    base.sky = None
    return base
