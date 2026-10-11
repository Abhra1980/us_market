"""NYSE trading days, 1999 onward, from the exchange's holiday rules plus its one-off closures.

Checked against Yahoo's ^GSPC trading days (research_c/yahoo_gspc/gspc.json, not in git):
``python3 sp500_history/membership/nyse_calendar.py`` prints every disagreement.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# Closures outside the holiday rules.
SPECIAL_CLOSURES = {
    date(2001, 9, 11), date(2001, 9, 12), date(2001, 9, 13), date(2001, 9, 14),  # 9/11
    date(2004, 6, 11),   # President Reagan's funeral
    date(2007, 1, 2),    # President Ford's funeral
    date(2012, 10, 29), date(2012, 10, 30),   # Hurricane Sandy
    date(2018, 12, 5),   # President G.H.W. Bush's funeral
    date(2025, 1, 9),    # President Carter's funeral
}


def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def _nth_weekday(y: int, month: int, weekday: int, n: int) -> date:
    """n-th weekday (Mon=0) of the month; n = -1 for the last."""
    if n > 0:
        d = date(y, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(y + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date | None:
    """Saturday holidays move to Friday, Sunday ones to Monday. NYSE does not move
    New Year's Day back into the old year, so a Saturday 1 Jan is simply lost."""
    if d.weekday() == 5:
        return None if (d.month, d.day) == (1, 1) else d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def holidays(y: int) -> frozenset[date]:
    fixed = [date(y, 1, 1), date(y, 7, 4), date(y, 12, 25)]
    if y >= 2022:
        fixed.append(date(y, 6, 19))    # Juneteenth, first observed 2022
    out = {o for o in map(_observed, fixed) if o}
    out |= {
        _nth_weekday(y, 1, 0, 3),       # Martin Luther King Jr. Day (NYSE from 1998)
        _nth_weekday(y, 2, 0, 3),       # Presidents' Day
        _easter(y) - timedelta(days=2), # Good Friday
        _nth_weekday(y, 5, 0, -1),      # Memorial Day
        _nth_weekday(y, 9, 0, 1),       # Labor Day
        _nth_weekday(y, 11, 3, 4),      # Thanksgiving
    }
    return frozenset(out | {d for d in SPECIAL_CLOSURES if d.year == y})


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def next_trading_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def on_or_after(d: date) -> date:
    return d if is_trading_day(d) else next_trading_day(d)


def on_or_before(d: date) -> date:
    return d if is_trading_day(d) else previous_trading_day(d)


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "research_c/yahoo_gspc/gspc.json"
    r = json.loads(path.read_text())["chart"]["result"][0]
    yahoo = {datetime.fromtimestamp(t, timezone.utc).date() for t in r["timestamp"]}
    last = max(yahoo)
    d, bad = date(1999, 1, 1), []
    while d <= last:
        if is_trading_day(d) != (d in yahoo):
            bad.append((d.isoformat(), "rules say open" if is_trading_day(d) else "rules say closed"))
        d += timedelta(days=1)
    print(f"1999-01-01..{last}: {len(bad)} disagreements with Yahoo ^GSPC")
    for b in bad:
        print("  ", *b)
