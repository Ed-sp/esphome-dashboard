"""The liturgical calendar, reduced to a lookup key.

Everything here is computed, not tabulated: Easter drives the movable feasts,
Advent Sunday is derived from Christmas Day, and the rest falls out of those two.
So the collects table needs no maintenance from year to year.

The key insight for sizing the table: in Anglican practice a Sunday's collect is
used through the following weekdays, so `key_for` resolves any date back to its
*controlling* day -- a principal feast if the date is one, otherwise the most
recent Sunday. That turns 365 entries into roughly 60.

Two deliberate simplifications, both documented rather than hidden:

*   Sundays between Epiphany and Ash Wednesday are all keyed `epiphany-N`.
    Common Worship splits the later ones off as Sundays before Lent; for a
    hallway panel that distinction is not worth the extra table entries.
*   The Annunciation is not transferred out of Holy Week or Easter week as the
    rules require. It is suppressed instead, so the season's own collect shows.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

SUNDAY = 6


@lru_cache(maxsize=64)
def easter(year: int) -> date:
    """Easter Day in the Gregorian calendar (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def advent_sunday(year: int) -> date:
    """The fourth Sunday before Christmas Day, which starts the liturgical year."""
    christmas_eve = date(year, 12, 24)
    advent_four = christmas_eve - timedelta(days=(christmas_eve.weekday() + 1) % 7)
    return advent_four - timedelta(days=21)


def _previous_sunday(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _fixed_feast(day: date) -> str | None:
    return {
        (12, 25): "christmas-day",
        (12, 26): "stephen",
        (1, 1): "naming-of-jesus",
        (1, 6): "epiphany",
        (2, 2): "presentation",
        (3, 25): "annunciation",
        (11, 1): "all-saints",
    }.get((day.month, day.day))


def _movable_feast(day: date) -> str | None:
    offsets = {
        -46: "ash-wednesday",
        -7: "palm-sunday",
        -3: "maundy-thursday",
        -2: "good-friday",
        -1: "holy-saturday",
        0: "easter-day",
        39: "ascension",
        49: "pentecost",
        56: "trinity-sunday",
    }
    delta = (day - easter(day.year)).days
    return offsets.get(delta)


def _classify_sunday(sunday: date) -> str:
    """Name a Sunday that is not itself a principal feast.

    Walks the liturgical year forwards from its own Advent Sunday, so every
    season is bounded at both ends. Testing only the lower bound is the easy
    mistake here: it puts August in the Christmas season.
    """
    this_advent = advent_sunday(sunday.year)
    advent = this_advent if sunday >= this_advent else advent_sunday(sunday.year - 1)

    christmas = date(advent.year, 12, 25)
    epiphany = date(advent.year + 1, 1, 6)

    if sunday < christmas:
        return f"advent-{(sunday - advent).days // 7 + 1}"

    if sunday < epiphany:
        # At most two Sundays fall between Christmas Day and Epiphany.
        return f"christmas-{((sunday - christmas).days + 6) // 7}"

    year = epiphany.year
    pascha = easter(year)
    lent_one = pascha - timedelta(days=42)

    if sunday < lent_one:
        return f"epiphany-{(sunday - epiphany).days // 7 + 1}"

    if sunday <= pascha - timedelta(days=14):
        return f"lent-{(sunday - lent_one).days // 7 + 1}"

    if pascha < sunday <= pascha + timedelta(days=42):
        return f"easter-{(sunday - pascha).days // 7 + 1}"

    # The last four Sundays of the year are counted backwards from Advent, so
    # this has to be tested before the Trinity numbering claims them.
    sundays_left = (advent_sunday(year) - sunday).days // 7
    if 1 <= sundays_left <= 4:
        return f"before-advent-{sundays_left}"

    trinity = pascha + timedelta(days=56)
    if sunday > trinity:
        return f"trinity-{(sunday - trinity).days // 7}"

    return "ordinary"


def key_for(day: date) -> str:
    """The collect key governing `day`."""

    def feast(when: date) -> str | None:
        movable = _movable_feast(when)
        if movable:
            return movable
        fixed = _fixed_feast(when)
        if fixed:
            # Holy Week and Easter Week outrank anything in the fixed calendar.
            pascha = easter(when.year)
            if pascha - timedelta(days=7) <= when <= pascha + timedelta(days=7):
                return None
            return fixed
        return None

    today = feast(day)
    if today:
        return today

    # A Sunday's collect carries through the following weekdays, and that Sunday
    # may itself have been a principal feast -- Easter Day governs Easter Monday.
    controlling = _previous_sunday(day)
    return feast(controlling) or _classify_sunday(controlling)


_TITLES = {
    "advent": "Advent",
    "christmas": "Christmas",
    "epiphany": "Epiphany",
    "lent": "Lent",
    "easter": "Easter",
    "trinity": "Trinity",
    "before-advent": "Before Advent",
}


def title_for(key: str) -> str:
    """A human label for a key, e.g. 'trinity-10' -> 'Trinity 10'."""
    stem, _, number = key.rpartition("-")
    if number.isdigit() and stem in _TITLES:
        return f"{_TITLES[stem]} {number}"
    return key.replace("-", " ").title()


def keys_in_year(year: int) -> list[tuple[date, str]]:
    """Every distinct key the calendar produces across `year`, in date order.

    Used by tools/liturgy_year.py to report which entries the collects table is
    still missing.
    """
    seen: dict[str, date] = {}
    day = date(year, 1, 1)
    while day <= date(year, 12, 31):
        key = key_for(day)
        seen.setdefault(key, day)
        day += timedelta(days=1)
    return sorted(((when, key) for key, when in seen.items()), key=lambda pair: pair[0])
