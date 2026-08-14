"""The 800x480 composition.

Coordinates are lifted straight from the approved mockup, so the constants below
can be compared against it line for line. Text positions are baselines.

Structure, from the design brief: the left column is *today, act now*; the right
column is *ahead, plan around*; the bottom band closes with the collect and the
week's numbers. Blocks that have nothing to say collapse rather than draw an
empty heading, which is what lets the panel go quiet on a dull Tuesday.
"""

from __future__ import annotations

from ..model import Alert, Commute, Day, Event, Panel
from . import icons
from .canvas import Canvas, Text, rain_level

W, H = 800, 480
M = 12  # outer margin

# Column geometry
SPLIT_X = 496
LEFT = (M, 484)
RIGHT = (512, 788)

# Bands
HEADER_RULE_Y = 40
COLUMN_TOP, COLUMN_BOTTOM = 48, 388
BOTTOM_RULE_Y = 392

# Type scale. Sizes are px; tracking is extra px between characters.
EYEBROW = Text("sans_bold", 10, tracking=1.5)
BODY = Text("sans", 13)
SMALL = Text("sans", 11)
TINY = Text("sans", 9)
LABEL = Text("sans_bold", 10, tracking=0.8)
SERIF = Text("serif", 13)


def _eyebrow(c: Canvas, x: float, y: float, text: str) -> None:
    c.text(x, y, text.upper(), EYEBROW)


def _knockout(c: Canvas, x: float, y: float, text: str, style: Text, pad: int = 2) -> None:
    """Centred text with the shading cleared behind it, for labels over the graph."""
    width = c.measure(text, style)
    ascent = style.size
    c.filled(x - width / 2 - pad, y - ascent, x + width / 2 + pad, y + 2, fill=255)
    c.text(x, y, text, style, anchor="center")


# ----------------------------------------------------------------- header


def _header(c: Canvas, p: Panel) -> None:
    c.text(M, 28, p.date_label, Text("sans_bold", 20))

    icon = icons.for_condition(p.now.condition, night=p.now.night)
    icons.paste(c.image, icon, 560, 6, 28)
    c.text(596, 30, f"{round(p.now.temperature)}°", Text("sans_bold", 26))

    c.text(RIGHT[1], 19, p.now.summary, SMALL, anchor="right")

    bits = []
    if p.now.feels_like is not None:
        bits.append(f"FEELS {round(p.now.feels_like)}°")
    if p.now.sunset:
        bits.append(f"SUNSET {p.now.sunset}")
    if bits:
        c.text(RIGHT[1], 33, "  ·  ".join(bits), Text("sans", 9, tracking=0.4), anchor="right")

    c.rule(M, HEADER_RULE_Y, RIGHT[1], HEADER_RULE_Y, weight=2)
    c.rule(SPLIT_X, COLUMN_TOP, SPLIT_X, COLUMN_BOTTOM, tone="light")


# ------------------------------------------------------------- graph band

GRAPH_X0, GRAPH_X1 = 16, 480
GRAPH_TOP, GRAPH_FLOOR = 80, 138  # temperature range maps between these
GRAPH_BASE = 146  # where the dithered fill stops
GRAPH_LABELS_Y = 156


def _graph(c: Canvas, p: Panel) -> None:
    _eyebrow(c, M, 60, "Next 24 hours")
    if p.rain_summary:
        c.text(LEFT[1], 60, p.rain_summary, Text("sans", 9, tracking=0.6), anchor="right")

    hours = p.hours
    if len(hours) < 2:
        return

    temps = [h.temperature for h in hours]
    lo, hi = min(temps), max(temps)
    span = (hi - lo) or 1
    step = (GRAPH_X1 - GRAPH_X0) / (len(hours) - 1)

    def x_at(i: int) -> float:
        return GRAPH_X0 + i * step

    def y_at(t: float) -> float:
        return GRAPH_FLOOR - (t - lo) * (GRAPH_FLOOR - GRAPH_TOP) / span

    points = [(x_at(i), y_at(h.temperature)) for i, h in enumerate(hours)]
    area = points + [(x_at(len(hours) - 1), GRAPH_BASE), (GRAPH_X0, GRAPH_BASE)]

    # Rain, as dither density under the curve. One slice per hour, each clipped to
    # the area so the shading takes the shape of the temperature trace.
    for i, hour in enumerate(hours):
        level = rain_level(hour.rain)
        if not level:
            continue
        c.dither_fill(
            level,
            clip=area,
            rect=(x_at(i) - step / 2, GRAPH_TOP - 4, x_at(i) + step / 2, GRAPH_BASE),
        )

    # Night boundaries. Drawn before the trace so the line stays on top.
    for i in range(1, len(hours)):
        if hours[i].night == hours[i - 1].night:
            continue
        boundary = x_at(i) - step / 2
        c.rule(boundary, GRAPH_TOP - 2, boundary, GRAPH_BASE, tone="dashed")
        glyph = "moon" if hours[i].night else "sun"
        c.image.paste(0, (round(boundary) + 3, GRAPH_TOP - 3), icons.render(glyph, 10))

    c.polyline(points, weight=2)
    c.rule(GRAPH_X0, GRAPH_BASE, x_at(len(hours) - 1), GRAPH_BASE)

    # Peak and trough sit against dithered shading, so both get a white knockout
    # behind them rather than relying on the fill happening to be light there.
    peak = max(range(len(hours)), key=lambda i: hours[i].temperature)
    trough = min(range(len(hours)), key=lambda i: hours[i].temperature)
    _knockout(c, x_at(peak), y_at(hi) - 6, f"{round(hi)}°", Text("sans_bold", 10))
    _knockout(c, x_at(trough), GRAPH_BASE - 3, f"{round(lo)}°", Text("sans_bold", 9))

    for i, hour in enumerate(hours):
        if hour.hour % 3 == 0:
            c.text(x_at(i), GRAPH_LABELS_Y, f"{hour.hour:02d}", Text("sans", 9, tracking=0.4), anchor="center")

    c.rule(M, 170, LEFT[1], 170, tone="light")


# ---------------------------------------------------------------- leaving

COMMUTE_ROWS = (198, 240)


def _leaving(c: Canvas, commutes: list[Commute]) -> None:
    if not commutes:
        return
    _eyebrow(c, M, 188, "Leaving")

    for row, commute in zip(COMMUTE_ROWS, commutes[:2]):
        icons.paste(c.image, commute.mode, M, row, 30)
        c.text(52, row + 12, f"{commute.who} → {commute.destination}", SMALL)
        end = c.text(52, row + 31, f"{commute.minutes} min", Text("sans_bold", 22))

        cursor = max(end + 14, 142)
        if commute.slow:
            chip = f"▲ +{commute.delta_minutes} min"
            width = c.measure(chip, Text("sans_bold", 11)) + 18
            c.box(cursor, row + 15, cursor + width, row + 34)
            c.text(cursor + width / 2, row + 28, chip, Text("sans_bold", 11), anchor="center")
            cursor += width + 10
        if commute.note:
            c.text(cursor, row + 28, commute.note, TINY)

    c.rule(M, 286, LEFT[1], 286, tone="light")


# -------------------------------------------------------------- needs you

ALERT_TOP = 312
ALERT_BAR_H = 26
ALERT_ROW_H = 24
ALERT_BOTTOM = 394  # last usable baseline before the bottom band's rule


def _needs_you(c: Canvas, alerts: list[Alert]) -> None:
    if not alerts:
        return
    _eyebrow(c, M, 304, "Needs you")

    y = ALERT_TOP
    for alert in alerts:
        if y + (ALERT_BAR_H if alert.urgent else ALERT_ROW_H) > ALERT_BOTTOM:
            break
        if alert.urgent:
            # The one place solid black is allowed. It has to be rare to keep working.
            c.filled(M, y, LEFT[1], y + ALERT_BAR_H)
            icons.paste(c.image, alert.icon, M + 8, y + 4, 18, invert=True)
            c.text(44, y + 18, alert.text.upper(), Text("sans_bold", 13, tracking=0.6), fill=255)
            y += ALERT_BAR_H + 8
        else:
            icons.paste(c.image, alert.icon, M + 2, y + 2, 18)
            c.text(40, y + 16, c.ellipsize(alert.text, BODY, LEFT[1] - 40), BODY)
            y += ALERT_ROW_H


# ------------------------------------------------------------- next 7 days

WEEK_TOP = 80
WEEK_STEP = 17


def _week(c: Canvas, week: list[Day]) -> None:
    _eyebrow(c, RIGHT[0], 60, "Next 7 days")

    for i, day in enumerate(week[:7]):
        y = WEEK_TOP + i * WEEK_STEP
        c.text(RIGHT[0], y, day.label.upper(), LABEL)
        icons.paste(c.image, icons.for_condition(day.condition), 562, y - 12, 14)
        if day.rain is not None and day.rain >= 30:
            c.text(586, y, f"{round(day.rain)}%", TINY)
        c.text(756, y, f"{round(day.high)}°", Text("sans_bold", 14), anchor="right")
        c.text(RIGHT[1], y, f"{round(day.low)}°", SMALL, anchor="right")

    c.rule(RIGHT[0], 196, RIGHT[1], 196, tone="light")


# ---------------------------------------------------------------- next up

EVENT_TOP = 230
EVENT_STEP = 32
BADGE_R = 8


def _next_up(c: Canvas, events: list[Event], sky: str | None) -> None:
    _eyebrow(c, RIGHT[0], 214, "Next up")

    for i, event in enumerate(events[:4]):
        cy = EVENT_TOP + i * EVENT_STEP
        c.draw.ellipse(
            [RIGHT[0] + 8 - BADGE_R, cy - BADGE_R, RIGHT[0] + 8 + BADGE_R, cy + BADGE_R],
            outline=0,
            width=1,
        )
        c.text(RIGHT[0] + 8, cy + 4, event.badge, Text("sans_bold", 10), anchor="center")
        c.text(536, cy, event.when.upper(), LABEL)
        c.text(536, cy + 15, c.ellipsize(event.title, BODY, RIGHT[1] - 536), BODY)

    if sky:
        icons.paste(c.image, "spark", RIGHT[0], 352, 13)
        c.text(530, 363, c.ellipsize(sky, SMALL, RIGHT[1] - 530), SMALL)


# ------------------------------------------------------------ bottom band

COLLECT_X = (M, 520)
STATS_X = (552, 788)
STAT_TOP = 428
STAT_STEP = 15

# (size, leading, max lines, first baseline). Tried in order; the first that
# holds the whole text wins. A collect runs anywhere from one sentence to a
# paragraph, so a fixed size would either clip the long ones mid-prayer or set
# the short ones far too small.
COLLECT_LADDER = [
    (13, 17, 3, 431),
    (12, 15, 4, 426),
    (11, 14, 5, 420),
    (10, 13, 5, 424),
]


def _fit_collect(c: Canvas, text: str, width: float):
    for size, leading, max_lines, first in COLLECT_LADDER:
        style = Text("serif", size)
        lines = c.wrap(text, style, width)
        if len(lines) <= max_lines:
            return style, lines, leading, first

    size, leading, max_lines, first = COLLECT_LADDER[-1]
    style = Text("serif", size)
    return style, c.wrap(text, style, width, max_lines=max_lines), leading, first


def _bottom(c: Canvas, p: Panel) -> None:
    c.rule(M, BOTTOM_RULE_Y, RIGHT[1], BOTTOM_RULE_Y, weight=2)

    if p.collect:
        _eyebrow(c, M, 410, p.collect.title)
        width = COLLECT_X[1] - COLLECT_X[0]
        style, lines, leading, first = _fit_collect(c, p.collect.text, width)
        for i, line in enumerate(lines):
            c.text(M, first + i * leading, line, style)

    if p.stats:
        c.rule(536, 400, 536, 472, tone="light")
        _eyebrow(c, STATS_X[0], 410, "This week")
        for i, stat in enumerate(p.stats[:4]):
            y = STAT_TOP + i * STAT_STEP
            c.text(STATS_X[0], y, stat.label, SMALL)
            c.text(STATS_X[1], y, stat.value, Text("sans_bold", 12), anchor="right")


# ------------------------------------------------------------------ entry


def render(p: Panel) -> Canvas:
    c = Canvas(W, H)
    _header(c, p)
    _graph(c, p)
    _leaving(c, p.commutes)
    _needs_you(c, p.alerts)
    _week(c, p.week)
    _next_up(c, p.events, p.sky)
    _bottom(c, p)
    return c
