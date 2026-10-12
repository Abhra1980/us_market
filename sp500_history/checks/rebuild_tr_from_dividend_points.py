#!/usr/bin/env python3
"""Rebuild the S&P 500 Total Return index from S&P's price index and its quarterly
dividend points index, and compare it with S&P's published Total Return level.

S&P's method (Index Mathematics methodology, "Total Return Calculations"):
    DTR_t = (Price_t + IndexDividend_t) / Price_{t-1} - 1,   TR_t = TR_{t-1} * (1 + DTR_t)
The quarterly dividend points index accumulates IndexDividend through the quarter and
resets after each quarterly expiry, so a day's index dividend is the day's increase in
dividend points, or the whole level on the day it resets.

Inputs are S&P DJI's own website exports (10 years each): S&P 500 (indexId 340),
S&P 500 TR (344) and S&P 500 Dividend Points Index (Quarterly) (386). They are NOT in
the repo: S&P's terms forbid storing them in a database or redistributing them.
Each file is either a two-column CSV (date,value) or the JSON a firecrawl scrape of the
export returns (a markdown table under "markdown").

Usage:
    python -I sp500_history/checks/rebuild_tr_from_dividend_points.py PRICE TR DIVPOINTS
"""
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y", "%d-%b-%Y")


def parse_date(text: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    return None


def rows(path: Path):
    if path.suffix.lower() == ".json":
        markdown = json.loads(path.read_text(encoding="utf-8"))["markdown"]
        for line in markdown.splitlines():
            yield [c.strip() for c in line.strip().strip("|").split("|")]
    else:
        with path.open(newline="", encoding="utf-8") as f:
            yield from csv.reader(f)


def series(path: Path) -> dict[date, float]:
    out = {}
    for cells in rows(path):
        if len(cells) < 2 or (d := parse_date(cells[0])) is None:
            continue
        try:
            out[d] = float(cells[1].replace(",", ""))
        except ValueError:
            continue
    return out


def main() -> None:
    price, tr, points = (series(Path(p)) for p in sys.argv[1:4])
    days = sorted(set(price) & set(tr) & set(points))
    print(f"days: {len(days)} ({days[0]} to {days[-1]}); "
          f"price {len(price)}, TR {len(tr)}, dividend points {len(points)}")

    level, worst, resets = tr[days[0]], 0.0, 0
    for prev, day in zip(days, days[1:]):
        if points[day] < points[prev]:
            dividend = points[day]
            resets += 1
        else:
            dividend = points[day] - points[prev]
        level *= (price[day] + dividend) / price[prev]
        worst = max(worst, abs(level / tr[day] - 1))

    print(f"quarterly resets: {resets}")
    print(f"rebuilt {level:.2f} vs published {tr[days[-1]]:.2f} on {days[-1]}")
    print(f"largest gap on any day: {worst * 1e4:.2f} bp")


if __name__ == "__main__":
    main()
