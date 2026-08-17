"""Which collect keys a year produces, and which the table is still missing.

    python tools/liturgy_year.py            # this year
    python tools/liturgy_year.py 2027       # any year
    python tools/liturgy_year.py --missing  # only the gaps
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panel import liturgy  # noqa: E402
from panel.sources import collect  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    only_missing = "--missing" in sys.argv
    year = int(args[0]) if args else date.today().year

    table = collect.load_collects()
    entries = liturgy.keys_in_year(year)

    print(f"Easter {year}: {liturgy.easter(year):%d %B}")
    print(f"Advent Sunday: {liturgy.advent_sunday(year):%d %B}")
    print(f"{len(entries)} distinct keys\n")

    missing = 0
    for when, key in entries:
        have = key in table
        if not have:
            missing += 1
        if only_missing and have:
            continue
        mark = "  " if have else "??"
        print(f"{mark} {when:%d %b}  {key:<20} {liturgy.title_for(key)}")

    covered = len(entries) - missing
    print(f"\n{covered}/{len(entries)} keys have a collect; {missing} fall back to a psalm or prayer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
