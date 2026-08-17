"""Where everything sits, per panel size.

The 7.5" V1 is 640x384 and the V2 is 800x480 -- exactly 0.8 in both directions,
same 5:3 aspect. It is tempting to scale, and wrong: 13px body text becomes
10.4px and the 9px labels become 7.2px, which in 1-bit with no antialiasing is
not small type, it is noise.

So the type scale barely moves between the two and the *content* gives way
instead. The small panel shows five days rather than seven, three events rather
than four, three stats rather than four, and two alerts rather than three. That
is the honest trade: a 640x384 panel is not a smaller version of the same
dashboard, it is a shorter one.

Everything is explicit rather than derived. A layout tuned by eye against a
1-bit rasteriser does not survive being reconstituted from ratios, and the
numbers are easier to argue with when you can see them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Type:
    """Point sizes, and the tracking that goes with the small-caps ones."""

    date: int
    now_temp: int
    now_summary: int
    now_detail: int

    eyebrow: int
    eyebrow_tracking: float

    graph_label: int
    graph_peak: int

    commute_name: int
    commute_time: int
    commute_chip: int
    commute_note: int

    alert_bar: int
    alert_row: int

    week_day: int
    week_rain: int
    week_high: int
    week_low: int

    event_badge: int
    event_when: int
    event_title: int
    sky: int

    stat_label: int
    stat_value: int


@dataclass(frozen=True)
class Geometry:
    name: str
    width: int
    height: int
    margin: int

    split_x: int
    left: tuple[int, int]
    right: tuple[int, int]
    header_rule_y: int
    column_top: int
    column_bottom: int

    # header
    date_baseline: int
    now_icon: tuple[int, int, int]  # x, y, size
    now_temp_x: int
    now_temp_baseline: int
    now_summary_baseline: int
    now_detail_baseline: int

    # 24-hour graph
    graph_eyebrow_y: int
    graph_x: tuple[int, int]
    graph_top: int
    graph_floor: int
    graph_base: int
    graph_labels_y: int
    graph_rule_y: int

    # leaving
    leaving_eyebrow_y: int
    commute_rows: tuple[int, ...]
    commute_icon: int
    commute_text_x: int
    commute_name_dy: int
    commute_time_dy: int
    commute_chip_dy: int
    commute_chip_h: int
    leaving_rule_y: int

    # needs you
    alerts_eyebrow_y: int
    alert_top: int
    alert_bar_h: int
    alert_row_h: int
    alert_bottom: int
    alert_icon: int

    # next N days
    week_eyebrow_y: int
    week_top: int
    week_step: int
    week_days: int
    week_icon_x: int
    week_icon: int
    week_rain_x: int
    week_high_x: int
    week_rule_y: int

    # next up
    events_eyebrow_y: int
    event_top: int
    event_step: int
    event_count: int
    event_badge_r: int
    event_text_x: int
    event_title_dy: int
    sky_icon_y: int
    sky_baseline: int
    sky_leading: int
    sky_lines: int

    # bottom band
    bottom_rule_y: int
    bottom_eyebrow_y: int
    collect_x: tuple[int, int]
    stats_divider_x: int
    stats_x: tuple[int, int]
    stat_top: int
    stat_step: int
    stat_count: int

    # (size, leading, max lines, first baseline), tried in order
    collect_ladder: tuple[tuple[int, int, int, int], ...]

    type: Type = field(repr=False)


# ----------------------------------------------------------------- 800 x 480

V2 = Geometry(
    name="800x480",
    width=800,
    height=480,
    margin=12,
    split_x=496,
    left=(12, 484),
    right=(512, 788),
    header_rule_y=40,
    column_top=48,
    column_bottom=388,
    date_baseline=28,
    now_icon=(560, 6, 28),
    now_temp_x=596,
    now_temp_baseline=30,
    now_summary_baseline=19,
    now_detail_baseline=33,
    graph_eyebrow_y=60,
    graph_x=(16, 480),
    graph_top=80,
    graph_floor=138,
    graph_base=146,
    graph_labels_y=156,
    graph_rule_y=170,
    leaving_eyebrow_y=188,
    commute_rows=(198, 240),
    commute_icon=30,
    commute_text_x=52,
    commute_name_dy=12,
    commute_time_dy=31,
    commute_chip_dy=15,
    commute_chip_h=19,
    leaving_rule_y=286,
    alerts_eyebrow_y=304,
    alert_top=312,
    alert_bar_h=26,
    alert_row_h=24,
    alert_bottom=394,
    alert_icon=18,
    week_eyebrow_y=60,
    week_top=80,
    week_step=17,
    week_days=7,
    week_icon_x=562,
    week_icon=14,
    week_rain_x=586,
    week_high_x=756,
    week_rule_y=196,
    events_eyebrow_y=214,
    event_top=230,
    event_step=32,
    event_count=4,
    event_badge_r=8,
    event_text_x=536,
    event_title_dy=15,
    sky_icon_y=352,
    sky_baseline=363,
    sky_leading=14,
    sky_lines=2,
    bottom_rule_y=392,
    bottom_eyebrow_y=410,
    collect_x=(12, 520),
    stats_divider_x=536,
    stats_x=(552, 788),
    stat_top=428,
    stat_step=15,
    stat_count=4,
    collect_ladder=((13, 17, 3, 431), (12, 15, 4, 426), (11, 14, 5, 420), (10, 13, 5, 424)),
    type=Type(
        date=20, now_temp=26, now_summary=11, now_detail=9,
        eyebrow=10, eyebrow_tracking=1.5,
        graph_label=9, graph_peak=10,
        commute_name=11, commute_time=22, commute_chip=11, commute_note=9,
        alert_bar=13, alert_row=13,
        week_day=11, week_rain=9, week_high=14, week_low=11,
        event_badge=10, event_when=10, event_title=13, sky=11,
        stat_label=11, stat_value=12,
    ),
)


# ----------------------------------------------------------------- 640 x 384
#
# 96px shorter and 160px narrower. The type scale gives up 1-2px in places; the
# content gives up two forecast days, one event, one stat and one alert.

V1 = Geometry(
    name="640x384",
    width=640,
    height=384,
    margin=10,
    split_x=396,
    left=(10, 386),
    right=(404, 630),
    header_rule_y=32,
    column_top=40,
    column_bottom=300,
    date_baseline=23,
    now_icon=(438, 3, 24),
    now_temp_x=468,
    now_temp_baseline=25,
    now_summary_baseline=15,
    now_detail_baseline=28,
    graph_eyebrow_y=48,
    graph_x=(14, 384),
    graph_top=62,
    graph_floor=106,
    graph_base=113,
    graph_labels_y=123,
    graph_rule_y=136,
    leaving_eyebrow_y=150,
    # Pulled 4px tighter than looks comfortable in isolation, so that the alert
    # block below clears two rows instead of one. A bin alert plus nothing else
    # is a worse panel than a slightly closer pair of commutes.
    commute_rows=(156, 192),
    commute_icon=26,
    commute_text_x=44,
    commute_name_dy=11,
    commute_time_dy=29,
    commute_chip_dy=14,
    commute_chip_h=18,
    leaving_rule_y=228,
    alerts_eyebrow_y=242,
    alert_top=250,
    alert_bar_h=24,
    alert_row_h=22,
    alert_bottom=304,
    alert_icon=16,
    week_eyebrow_y=48,
    week_top=66,
    week_step=16,
    week_days=5,
    week_icon_x=452,
    week_icon=13,
    week_rain_x=474,
    week_high_x=600,
    week_rule_y=156,
    events_eyebrow_y=172,
    event_top=188,
    event_step=30,
    event_count=3,
    event_badge_r=7,
    event_text_x=424,
    event_title_dy=14,
    sky_icon_y=272,
    sky_baseline=282,
    sky_leading=13,
    sky_lines=2,
    bottom_rule_y=306,
    bottom_eyebrow_y=322,
    collect_x=(10, 396),
    stats_divider_x=408,
    stats_x=(420, 630),
    stat_top=338,
    stat_step=14,
    stat_count=3,
    collect_ladder=((12, 15, 3, 340), (11, 13, 4, 336), (10, 12, 4, 338), (9, 11, 5, 334)),
    type=Type(
        date=17, now_temp=22, now_summary=10, now_detail=8,
        eyebrow=9, eyebrow_tracking=1.2,
        graph_label=8, graph_peak=9,
        # The note sits in ~200px of clear space, so it can afford 9px; at 8 it
        # read as crowding the chip when it was only small.
        commute_name=10, commute_time=19, commute_chip=10, commute_note=9,
        alert_bar=12, alert_row=12,
        week_day=10, week_rain=8, week_high=13, week_low=10,
        event_badge=9, event_when=9, event_title=12, sky=10,
        stat_label=10, stat_value=11,
    ),
)


PRESETS = {"800x480": V2, "640x384": V1}


def for_size(width: int, height: int) -> Geometry:
    key = f"{width}x{height}"
    if key not in PRESETS:
        raise ValueError(
            f"No layout tuned for {key}. Available: {', '.join(sorted(PRESETS))}. "
            f"Add a preset in geometry.py rather than scaling an existing one -- "
            f"1-bit type does not survive being multiplied by 0.8."
        )
    return PRESETS[key]
