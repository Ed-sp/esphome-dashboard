"""The composition, for whichever panel size it is drawn at.

Structure, from the design brief: the left column is *today, act now*; the right
column is *ahead, plan around*; the bottom band closes with the collect and the
week's numbers. Blocks with nothing to say collapse rather than draw an empty
heading, which is what lets the panel go quiet on a dull Tuesday.

Every coordinate and type size comes from `geometry.Geometry`. Two presets exist
-- 800x480 and 640x384 -- and they are separately tuned rather than scaled; see
that module for why.
"""

from __future__ import annotations

from ..model import Alert, Commute, Day, Event, Panel
from . import icons
from .canvas import Canvas, Text, rain_level
from .geometry import Geometry, V2, for_size

SERIF = "serif"


def _eyebrow(c: Canvas, g: Geometry, x: float, y: float, text: str) -> None:
    c.text(x, y, text.upper(), Text("sans_bold", g.type.eyebrow, tracking=g.type.eyebrow_tracking))


def _knockout(c: Canvas, x: float, y: float, text: str, style: Text, pad: int = 2) -> None:
    """Centred text with the shading cleared behind it, for labels over the graph."""
    width = c.measure(text, style)
    c.filled(x - width / 2 - pad, y - style.size, x + width / 2 + pad, y + 2, fill=255)
    c.text(x, y, text, style, anchor="center")


# ----------------------------------------------------------------- header


def _header(c: Canvas, g: Geometry, p: Panel) -> None:
    c.text(g.margin, g.date_baseline, p.date_label, Text("sans_bold", g.type.date))

    icon = icons.for_condition(p.now.condition, night=p.now.night)
    icons.paste(c.image, icon, *g.now_icon[:2], g.now_icon[2])
    temperature = c.text(
        g.now_temp_x, g.now_temp_baseline,
        f"{round(p.now.temperature)}°", Text("sans_bold", g.type.now_temp),
    )

    # The two lines to the right of the temperature are right-aligned to the
    # margin, so their room depends on how wide the temperature rendered. That
    # varies with typeface and with "-9°" versus "7°". Measure it.
    available = g.right[1] - temperature - 10
    summary = Text("sans", g.type.now_summary)
    c.text(g.right[1], g.now_summary_baseline, c.ellipsize(p.now.summary, summary, available),
           summary, anchor="right")

    detail = Text("sans", g.type.now_detail, tracking=0.4)
    bits = []
    if p.now.feels_like is not None:
        bits.append(f"FEELS {round(p.now.feels_like)}°")
    if p.now.sunset:
        bits.append(f"SUNSET {p.now.sunset}")
    # Drop whole clauses rather than ellipsizing: "FEELS 15° · SUNS…" is worse
    # than just the sunset time.
    while bits and c.measure("  ·  ".join(bits), detail) > available:
        bits.pop(0)
    if bits:
        c.text(g.right[1], g.now_detail_baseline, "  ·  ".join(bits), detail, anchor="right")

    c.rule(g.margin, g.header_rule_y, g.right[1], g.header_rule_y, weight=2)
    c.rule(g.split_x, g.column_top, g.split_x, g.column_bottom, tone="light")


# ------------------------------------------------------------- graph band


def _graph(c: Canvas, g: Geometry, p: Panel) -> None:
    _eyebrow(c, g, g.margin, g.graph_eyebrow_y, "Next 24 hours")
    if p.rain_summary:
        c.text(g.left[1], g.graph_eyebrow_y, p.rain_summary,
               Text("sans", g.type.graph_label, tracking=0.5), anchor="right")

    hours = p.hours
    if len(hours) < 2:
        return

    temps = [h.temperature for h in hours]
    lo, hi = min(temps), max(temps)
    span = (hi - lo) or 1
    x0, x1 = g.graph_x
    step = (x1 - x0) / (len(hours) - 1)

    def x_at(i: int) -> float:
        return x0 + i * step

    def y_at(t: float) -> float:
        return g.graph_floor - (t - lo) * (g.graph_floor - g.graph_top) / span

    points = [(x_at(i), y_at(h.temperature)) for i, h in enumerate(hours)]
    area = points + [(x_at(len(hours) - 1), g.graph_base), (x0, g.graph_base)]

    # Rain, as dither density under the curve. One slice per hour, each clipped
    # to the area so the shading takes the shape of the temperature trace.
    for i, hour in enumerate(hours):
        level = rain_level(hour.rain)
        if not level:
            continue
        c.dither_fill(level, clip=area,
                      rect=(x_at(i) - step / 2, g.graph_top - 4, x_at(i) + step / 2, g.graph_base))

    # Night boundaries, drawn before the trace so the line stays on top.
    for i in range(1, len(hours)):
        if hours[i].night == hours[i - 1].night:
            continue
        boundary = x_at(i) - step / 2
        c.rule(boundary, g.graph_top - 2, boundary, g.graph_base, tone="dashed")
        glyph = "moon" if hours[i].night else "sun"
        c.image.paste(0, (round(boundary) + 3, g.graph_top - 3), icons.render(glyph, 10))

    c.polyline(points, weight=2)
    c.rule(x0, g.graph_base, x_at(len(hours) - 1), g.graph_base)

    peak = max(range(len(hours)), key=lambda i: hours[i].temperature)
    trough = min(range(len(hours)), key=lambda i: hours[i].temperature)
    _knockout(c, x_at(peak), y_at(hi) - 6, f"{round(hi)}°", Text("sans_bold", g.type.graph_peak))
    _knockout(c, x_at(trough), g.graph_base - 3, f"{round(lo)}°",
              Text("sans_bold", g.type.graph_peak - 1))

    labels = Text("sans", g.type.graph_label, tracking=0.4)
    # Every third hour at full size; every sixth when the panel is narrow enough
    # that they would otherwise collide.
    every = 3 if step * 3 >= 34 else 6
    for i, hour in enumerate(hours):
        if hour.hour % every == 0:
            c.text(x_at(i), g.graph_labels_y, f"{hour.hour:02d}", labels, anchor="center")

    c.rule(g.margin, g.graph_rule_y, g.left[1], g.graph_rule_y, tone="light")


# ---------------------------------------------------------------- leaving


def _leaving(c: Canvas, g: Geometry, commutes: list[Commute]) -> None:
    if not commutes:
        return
    _eyebrow(c, g, g.margin, g.leaving_eyebrow_y, "Leaving")

    for row, commute in zip(g.commute_rows, commutes):
        icons.paste(c.image, commute.mode, g.margin, row, g.commute_icon)
        c.text(g.commute_text_x, row + g.commute_name_dy,
               f"{commute.who} → {commute.destination}", Text("sans", g.type.commute_name))
        end = c.text(g.commute_text_x, row + g.commute_time_dy,
                     f"{commute.minutes} min", Text("sans_bold", g.type.commute_time))

        cursor = end + 12
        chip = Text("sans_bold", g.type.commute_chip)
        if commute.slow:
            text = f"▲ +{commute.delta_minutes} min"
            width = c.measure(text, chip) + 16
            top = row + g.commute_chip_dy
            c.box(cursor, top, cursor + width, top + g.commute_chip_h)
            c.text(cursor + width / 2, top + g.commute_chip_h - 6, text, chip, anchor="center")
            cursor += width + 8
        if commute.note:
            note = Text("sans", g.type.commute_note)
            room = g.left[1] - cursor
            if room > 40:
                c.text(cursor, row + g.commute_time_dy - 3,
                       c.ellipsize(commute.note, note, room), note)

    c.rule(g.margin, g.leaving_rule_y, g.left[1], g.leaving_rule_y, tone="light")


# -------------------------------------------------------------- needs you


def _needs_you(c: Canvas, g: Geometry, alerts: list[Alert]) -> None:
    if not alerts:
        return
    _eyebrow(c, g, g.margin, g.alerts_eyebrow_y, "Needs you")

    y = g.alert_top
    for alert in alerts:
        height = g.alert_bar_h if alert.urgent else g.alert_row_h
        if y + height > g.alert_bottom:
            break
        if alert.urgent:
            # The one place solid black is allowed. It has to be rare to work.
            c.filled(g.margin, y, g.left[1], y + height)
            icons.paste(c.image, alert.icon, g.margin + 6, y + 4, g.alert_icon, invert=True)
            c.text(g.margin + 6 + g.alert_icon + 8, y + height - 8, alert.text.upper(),
                   Text("sans_bold", g.type.alert_bar, tracking=0.6), fill=255)
            y += height + 6
        else:
            icons.paste(c.image, alert.icon, g.margin + 2, y + 2, g.alert_icon)
            style = Text("sans", g.type.alert_row)
            x = g.margin + 2 + g.alert_icon + 8
            c.text(x, y + g.alert_icon - 2, c.ellipsize(alert.text, style, g.left[1] - x), style)
            y += height


# ------------------------------------------------------------ next N days


def _week(c: Canvas, g: Geometry, week: list[Day]) -> None:
    _eyebrow(c, g, g.right[0], g.week_eyebrow_y, f"Next {g.week_days} days")

    for i, day in enumerate(week[: g.week_days]):
        y = g.week_top + i * g.week_step
        c.text(g.right[0], y, day.label.upper(),
               Text("sans_bold", g.type.week_day, tracking=0.8))
        icons.paste(c.image, icons.for_condition(day.condition),
                    g.week_icon_x, y - g.week_icon + 2, g.week_icon)
        if day.rain_label:
            c.text(g.week_rain_x, y, day.rain_label, Text("sans", g.type.week_rain))
        c.text(g.week_high_x, y, f"{round(day.high)}°",
               Text("sans_bold", g.type.week_high), anchor="right")
        c.text(g.right[1], y, f"{round(day.low)}°",
               Text("sans", g.type.week_low), anchor="right")

    c.rule(g.right[0], g.week_rule_y, g.right[1], g.week_rule_y, tone="light")


# ---------------------------------------------------------------- next up


def _next_up(c: Canvas, g: Geometry, events: list[Event], sky: str | None) -> None:
    # A heading with nothing under it looks like a fault rather than a quiet
    # day, so the whole block goes if there is neither an event nor a sky line.
    if not events and not sky:
        return
    _eyebrow(c, g, g.right[0], g.events_eyebrow_y, "Next up")

    r = g.event_badge_r
    body = Text("sans", g.type.event_title)
    for i, event in enumerate(events[: g.event_count]):
        cy = g.event_top + i * g.event_step
        cx = g.right[0] + r
        c.draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, width=1)
        c.text(cx, cy + r // 2, event.badge, Text("sans_bold", g.type.event_badge), anchor="center")
        c.text(g.event_text_x, cy, event.when.upper(),
               Text("sans_bold", g.type.event_when, tracking=0.8))
        c.text(g.event_text_x, cy + g.event_title_dy,
               c.ellipsize(event.title, body, g.right[1] - g.event_text_x), body)

    if sky:
        # Two lines, because the eclipse entries carry the detail that makes
        # them worth acting on -- what time, and whether it will still be up.
        style = Text("sans", g.type.sky)
        icons.paste(c.image, "spark", g.right[0], g.sky_icon_y, 13)
        x = g.right[0] + 18
        for i, line in enumerate(c.wrap(sky, style, g.right[1] - x, max_lines=g.sky_lines)):
            c.text(x, g.sky_baseline + i * g.sky_leading, line, style)


# ------------------------------------------------------------ bottom band


def _fit_collect(c: Canvas, g: Geometry, text: str, width: float):
    """The largest rung of the ladder that holds the whole prayer."""
    for size, leading, max_lines, first in g.collect_ladder:
        style = Text(SERIF, size)
        lines = c.wrap(text, style, width)
        if len(lines) <= max_lines:
            return style, lines, leading, first

    size, leading, max_lines, first = g.collect_ladder[-1]
    style = Text(SERIF, size)
    return style, c.wrap(text, style, width, max_lines=max_lines), leading, first


def _bottom(c: Canvas, g: Geometry, p: Panel) -> None:
    c.rule(g.margin, g.bottom_rule_y, g.right[1], g.bottom_rule_y, weight=2)

    if p.collect:
        _eyebrow(c, g, g.margin, g.bottom_eyebrow_y, p.collect.title)
        width = g.collect_x[1] - g.collect_x[0]
        style, lines, leading, first = _fit_collect(c, g, p.collect.text, width)
        for i, line in enumerate(lines):
            c.text(g.margin, first + i * leading, line, style)

    if p.stats:
        c.rule(g.stats_divider_x, g.bottom_rule_y + 8, g.stats_divider_x, g.height - 8, tone="light")
        _eyebrow(c, g, g.stats_x[0], g.bottom_eyebrow_y, "This week")
        label = Text("sans", g.type.stat_label)
        value = Text("sans_bold", g.type.stat_value)
        for i, stat in enumerate(p.stats[: g.stat_count]):
            y = g.stat_top + i * g.stat_step
            c.text(g.stats_x[0], y, stat.label, label)
            c.text(g.stats_x[1], y, stat.value, value, anchor="right")


# ------------------------------------------------------------------ entry


def render(p: Panel, geometry: Geometry | None = None) -> Canvas:
    g = geometry or V2
    c = Canvas(g.width, g.height)
    _header(c, g, p)
    _graph(c, g, p)
    _leaving(c, g, p.commutes)
    _needs_you(c, g, p.alerts)
    _week(c, g, p.week)
    _next_up(c, g, p.events, p.sky)
    _bottom(c, g, p)
    return c


__all__ = ["render", "Geometry", "for_size", "V2"]
