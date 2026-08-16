"""What the sky line would say across a year, and which provider said it.

    python tools/sky_year.py                 # this year, panel.yaml settings
    python tools/sky_year.py 2027
    python tools/sky_year.py --off moon      # as if the moon provider were off

Useful for deciding whether a provider earns its place before committing to it:
if `moon` fills two months of the year with "Full moon Tuesday", that is worth
knowing before it is on a wall.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panel.config import load  # noqa: E402
from panel.sources import sky  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    years = [int(a) for a in argv if a.isdigit()] or [date.today().year]
    disabled = {argv[i + 1] for i, a in enumerate(argv) if a == "--off" and i + 1 < len(argv)}

    settings = (load().raw.get("sky") or {})
    events_config = dict(settings.get("events") or {})
    for name in disabled:
        events_config[name] = {**(events_config.get(name) or {}), "enabled": False}

    active = [
        name
        for name in sky.providers()
        if (events_config.get(name) or {}).get("enabled", True)
    ]
    print(f"providers: {', '.join(sky.providers())}")
    print(f"enabled:   {', '.join(active) or '(none)'}\n")

    for year in years:
        counts: Counter[str] = Counter()
        shown: list[tuple[date, str]] = []
        day = date(year, 1, 1)
        while day <= date(year, 12, 31):
            events = sky.collect_events(
                day, days=settings.get("lookahead_days", 7), config=events_config
            )
            if events:
                counts[_bucket(events[0].text)] += 1
                if not shown or shown[-1][1] != events[0].text:
                    shown.append((day, events[0].text))
            else:
                counts["(nothing)"] += 1
            day += timedelta(days=1)

        print(f"{year}: days by what the line shows")
        for label, count in counts.most_common():
            print(f"  {label:<12} {count:>3}")
        print(f"  {len(shown)} distinct lines\n")

    return 0


def _bucket(text: str) -> str:
    lowered = text.lower()
    for needle, label in (
        ("aurora", "aurora"),
        ("eclipse", "eclipse"),
        ("full moon", "moon"),
    ):
        if needle in lowered:
            return label
    return "shower"


if __name__ == "__main__":
    raise SystemExit(main())
