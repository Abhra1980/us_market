#!/usr/bin/env python3
"""Point-in-time S&P 500 membership, 2010 to today, into schema usmarket.

THE SOURCES
-----------
* S&P DJI's own press releases, 2010 onward (``fetch_sp_press.py`` ->
  data/sp500_changes_2010_2026.csv): every addition and deletion with S&P's effective date.
* Full holdings of five full-replication S&P 500 funds from SEC Form NPORT-P, one list per
  fund quarter, together every month-end from Sep 2019 (``fetch_sec_holdings.py`` ->
  downloads/sec/nport_holdings.csv). Funds file CUSIPs, not tickers.
* The SEC's fails-to-deliver files (same script -> downloads/sec/ftd_cusip_symbol.csv):
  which ticker each CUSIP traded under, and when. This turns fund lists into tickers and
  dates the ticker changes S&P announced without a date.

THE METHOD
----------
Every membership change comes from S&P's text. The funds only check it:

1. Anchor: the securities at least two of SPY, Vanguard 500 and IVV held on 30 Jun 2026.
2. Roll S&P's changes forward to today and back to Jan 2010 from that anchor, with each
   member's ticker changes applied on the day the SEC data first shows the new ticker.
3. At every fund month-end from Sep 2019, compare the roll with the funds' list. A stretch
   between two month-ends that both match exactly is written as verified. Everything that
   does not match is recorded in index_membership_reconciliation, never smoothed over.

Index funds trade at the close before a change takes effect, so a fund list dated D is
compared with the composition effective on the next trading day after D.

Before Sep 2019 there are no fund lists with CUSIPs yet, so 2010-2019 is S&P's notices
rolled back from the 2019 lists, unverified.

Usage:
    python3 sp500_history/membership/build_sp500_modern.py --dry-run
    python3 sp500_history/membership/build_sp500_modern.py
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nyse_calendar import next_trading_day, on_or_after, previous_trading_day  # noqa: E402

DEFAULT_DSN = "postgresql://abhrajitpal@127.0.0.1:5434/market_pulse"
INDEX = "SP500"
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SEC = REPO / "sp500_history/downloads/sec"
CHANGES = HERE / "data/sp500_changes_2010_2026.csv"
TICKER_CHANGES = HERE / "data/sp500_ticker_changes_2010_2026.csv"
START = date(2010, 1, 4)                 # first trading day of 2010
ANCHOR_PERIOD = date(2026, 6, 30)
ANCHOR_FUNDS = ("SPY", "VFIAX", "IVV")
FTD_WINDOW = 60                          # days either side of a date a CUSIP->ticker pair may be used
SOURCE_PRESS = "sp_press_2010_2026"
SOURCE_FUNDS = "sec_nport_sp500_funds"
SOURCE_FTD = "sec_fails_to_deliver"
SOURCE_NAMES = "sec_ncsr_nq_sp500_funds_2010_2019"
NAME_SUMMARY = HERE / "data/fund_lists_2010_2019_summary.csv"    # fetch_sec_fundlists_2002_2009.py --from/--to
NAME_HOLDINGS = SEC / "fund_holdings_2010_2019.csv"

# Members filed by every fund with no CUSIP and no ticker the SEC data knows.
ISIN_TICKER = {
    "IE00B6330302": ("IR", date(2020, 3, 2), "Ingersoll-Rand plc: no CUSIP in any filing and absent from the SEC fails "
                           "files; S&P lists it as IR until it became Trane Technologies (TT) in 2020"),
}
# Replacements the fund lists show that S&P's press archive has no release for (S&P handled
# them through index notices on its own site). Dated by the SEC fails data, not by S&P.
NO_RELEASE_REPLACEMENTS = [
    # old, new, what, dated by: the new ticker's first trade, or the day after the old one's last
    ("MYL", "VTRS", "Mylan N.V. -> Viatris Inc. (Mylan-Upjohn combination, Nov 2020)", "new_first"),
    ("WRK", "SW", "WestRock Co. -> Smurfit Westrock plc (combination, Jul 2024)", "new_first"),
    ("PARA", "PSKY", "Paramount Global -> Paramount Skydance Corp. (Skydance merger, Aug 2025)", "new_first"),
    ("ITT", "XYL", "ITT split in three; Xylem replaced ITT (Oct 2011); ITT went to the MidCap 400", "new_first"),
    ("SII", "TYC", "Tyco International replaced Smith International on its acquisition by Schlumberger (Aug 2010)",
     "old_last"),
    ("PX", "LIN", "Praxair -> Linde plc (Praxair-Linde AG merger, Oct 2018)", "new_first"),
]
# "Date to be announced" changes whose deleted member kept trading (it moved to another
# index), so its own last trade says nothing. Dated instead by the last trade of the company
# whose acquisition triggered the change. The link is general knowledge, not S&P's text.
TBD_TRIGGER = {"BIG": ("WRC", "PVH's acquisition of Warnaco (WRC) triggered PVH replacing Big Lots")}
# S&P rows whose ticker S&P did not print. The 2015 rows: S&P prints each member's pair
# ("CMCSA/CMCSK") and says the member gets an "additional listed share class line", so the
# added line is the second ticker. Google: the Class C line distributed on 2 Apr 2014.
FILL_TICKER = {
    ("2014-04-03", "Google"): ("GOOG", "Class C line; ticker GOOG from the SEC fails data (class C CUSIP 38259P706)"),
    ("2015-09-21", "Comcast"): ("CMCSK", "second of S&P's printed pair CMCSA/CMCSK"),
    ("2015-09-21", "Twenty-First Century Fox"): ("FOX", "second of S&P's printed pair FOXA/FOX"),
    ("2015-09-21", "News Corp"): ("NWS", "second of S&P's printed pair NWSA/NWS"),
}
# Ticker changes with a new CUSIP that S&P's press archive has no release for (the press
# fetch lists them as missing). Dated by the new ticker's first sighting in the SEC data.
NO_RELEASE_RENAMES = [
    # Renames with a new CUSIP before the fund lists start (Sep 2019). S&P does not announce a
    # rename; the SEC's EDGAR records the same filer (CIK) under its former name.
    ("TMK", "GL", "Torchmark -> Globe Life (EDGAR CIK 320335, former name to 2019-08)"),
    ("HRS", "LHX", "Harris -> L3Harris (EDGAR CIK 202058, former name to 2019-06)"),
    ("PCLN", "BKNG", "Priceline -> Booking Holdings (EDGAR CIK 1075531, former name to 2018-02)"),
    ("COH", "TPR", "Coach -> Tapestry (EDGAR CIK 1116132, former name to 2017-10)"),
    ("MHP", "MHFI", "McGraw-Hill -> McGraw Hill Financial (EDGAR CIK 64040, former name to 2013-04)"),
    ("MHFI", "SPGI", "McGraw Hill Financial -> S&P Global (EDGAR CIK 64040, former name to 2016-05)"),
    ("LUK", "JEF", "Leucadia -> Jefferies Financial Group (EDGAR CIK 96223, former name to 2018-05)"),
    ("WPO", "GHC", "Washington Post -> Graham Holdings (EDGAR CIK 104889, former name to 2013-11)"),
    ("NU", "ES", "Northeast Utilities -> Eversource (EDGAR CIK 72741)"),
    ("MOT", "MSI", "Motorola -> Motorola Solutions (EDGAR CIK 68505, former name to 2011-01)"),
    ("WPI", "ACT", "Watson Pharmaceuticals -> Actavis Inc. (EDGAR CIK 884629, former name to 2013-01)"),
    ("FO", "BEAM", "Fortune Brands -> Beam Inc. (EDGAR CIK 789073, former name to 2011-10)"),
    ("NWSA", "FOXA", "News Corp -> Twenty-First Century Fox (EDGAR CIK 1308161, former name to 2013-06)"),
    ("TSO", "ANDV", "Tesoro -> Andeavor (EDGAR CIK 50104, former name to 2017-08)"),
    ("WLP", "ANTM", "WellPoint -> Anthem (EDGAR CIK 1156039, former name to 2014-11)"),
    ("WAG", "WBA", "Walgreen Co. -> Walgreens Boots Alliance (new holding company, Dec 2014)"),
    ("MWV", "WRK", "MeadWestvaco + Rock-Tenn -> WestRock (Jul 2015); index line taken as MeadWestvaco's "
                   "(general knowledge)"),
    ("ACT", "AGN", "Actavis plc renamed Allergan plc (Jun 2015)"),
    ("KRFT", "KHC", "Kraft Foods Group -> Kraft Heinz (Jul 2015)"),
    ("AMSG", "EVHC", "AmSurg -> Envision Healthcare (Dec 2016)"),
    ("CSC", "DXC", "Computer Sciences -> DXC Technology (Apr 2017)"),
    ("BHI", "BHGE", "Baker Hughes -> Baker Hughes, a GE company (Jul 2017)"),
    ("Q", "IQV", "Quintiles IMS -> IQVIA (Nov 2017)"),
    ("KORS", "CPRI", "Michael Kors -> Capri Holdings (Jan 2019)"),
]
# Share-class lines S&P's archive has no release for. Dated by the SEC data: an addition by
# the line's first sighting, a deletion by the day after its last trade.
NO_RELEASE_LINES = [
    ("include", "UAC", "Under Armour Class C line added (Apr 2016); traded as UAC until Dec 2016"),
    ("exclude", "CMCSK", "Comcast Special Class A line removed when the class was collapsed (Dec 2015)"),
]
# The SEC first shows class A as GOOGL on 7 Apr 2014; it changed on the Class C distribution.
RENAME_DATE = {
    ("GOOG", "GOOGL"): (date(2014, 4, 3), "class A became GOOGL when the Class C line (S&P effective "
                                          "3 Apr 2014) took GOOG"),
    ("NWSA", "FOXA"): (date(2013, 7, 1), "old News Corp became FOXA on the day S&P added the new News Corp "
                                         "under NWSA (S&P effective 1 Jul 2013); SEC data first shows FOXA 3 Jul"),
}
# A fund that systematically leaves out an index line. Seen in every one of its lists over the
# stretch, so its month-ends still check everything else; the excused lines are named in the note.
FUND_KNOWN_OMISSIONS = {
    "SWPPX": ({"FOX", "NWS"}, date(2023, 10, 1),
              "Schwab's fund holds one Fox line (FOXA) and one News Corp line (NWSA) from Oct 2023"),
}
SETTLEMENT_LAG = ((date(2017, 9, 5), 3), (date(2024, 5, 28), 2), (date.max, 1))   # T+3, T+2, T+1

SOURCES = [
    (SOURCE_PRESS, "S&P", "change_list", "sp500_history/membership/data/sp500_changes_2010_2026.csv",
     "https://press.spglobal.com/index.php?s=2429", None,
     "S&P DJI press releases (S&P Global archive from Jan 2012, PR Newswire 2010-2011)"),
    (SOURCE_FUNDS, "SPY, Vanguard 500, Fidelity 500, Schwab S&P 500, IVV (SEC NPORT-P)", "fund_holdings",
     "sp500_history/downloads/sec/nport_holdings.csv", "https://www.sec.gov/cgi-bin/browse-edgar", None,
     "Quarterly full holdings per fund; together every month-end from 2019-09. Checkpoints only"),
    (SOURCE_NAMES, "Vanguard 500, Vanguard Institutional, Fidelity 500, Schwab S&P 500, SPY, IVV (SEC N-CSR/N-Q)",
     "fund_holdings", "sp500_history/downloads/sec/fund_holdings_2010_2019.csv",
     "https://www.sec.gov/cgi-bin/browse-edgar", None,
     "Full holdings schedules by name, 2010-2019, before NPORT-P; matched to tickers through the SEC fails data. "
     "Checkpoints only"),
    (SOURCE_FTD, "SEC", "constituent_list", "sp500_history/downloads/sec/ftd_cusip_symbol.csv",
     "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data", None,
     "CUSIP <-> ticker pairs with first/last settlement date; used to name fund holdings"),
]


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


# Nasdaq's when-issued tickers for spin-offs end in V; S&P printed these. (FFIV, SOLV, VEEV
# and ANDV are real tickers, so the V is not stripped in general.)
NASDAQ_WHEN_ISSUED = {"TRIPV", "KRFTV", "NWSAV", "NAVIV", "PYPLV"}


def key(sym: str) -> str:
    """One spelling per ticker: S&P writes BRK.B, QEPwi and PYPLV, the SEC BRKB and PYPL."""
    k = re.sub(r"[^A-Z0-9]", "", re.sub(r"wi$", "", sym.strip())).upper()
    return k[:-1] if k in NASDAQ_WHEN_ISSUED else k


@dataclass(frozen=True)
class Change:
    effective: date
    action: str            # include | exclude
    symbol: str
    company: str
    announced: date | None
    url: str
    note: str


def load_changes() -> tuple[list[Change], list[dict]]:
    """S&P's dated rows. A change S&P repeated in a second release is kept once."""
    ok, skipped, seen = [], [], set()
    for r in csv.DictReader(CHANGES.open()):
        fill = next((v for (d, co), v in FILL_TICKER.items()
                     if r["effective_date"] == d and r["company"].startswith(co) and not r["symbol"]), None)
        if fill:
            r = {**r, "symbol": fill[0], "note": f"{r['note']} [ticker filled: {fill[1]}]"}
        if r["status"] != "ok" or not r["symbol"] or not r["effective_date"]:
            skipped.append(r)
            continue
        once = (r["effective_date"], r["action"], key(r["symbol"]))
        if once in seen:
            continue
        seen.add(once)
        ok.append(Change(date.fromisoformat(r["effective_date"]), r["action"], r["symbol"].strip(),
                         r["company"], date.fromisoformat(r["announced_date"]) if r["announced_date"] else None,
                         r["release_url"], r["note"]))
    return ok, skipped


def load_ftd() -> dict[str, list[tuple[str, date, date, str]]]:
    out: dict[str, list] = defaultdict(list)
    for r in csv.DictReader((SEC / "ftd_cusip_symbol.csv").open()):
        if r["placeholder"] != "Y":
            out[r["cusip"]].append((r["symbol"], date.fromisoformat(r["first_seen"]),
                                    date.fromisoformat(r["last_seen"]), r["description"]))
    return out


def symbol_at(pairs: list, d: date) -> tuple[str, date] | None:
    """The ticker this CUSIP traded under nearest to d (within FTD_WINDOW days), and since when."""
    best = None
    for sym, first, last, _ in pairs:
        gap = 0 if first <= d <= last else min(abs((d - first).days), abs((d - last).days))
        if gap <= FTD_WINDOW and (best is None or (gap, -first.toordinal()) < best[0]):
            best = ((gap, -first.toordinal()), sym, first)
    return (best[1], best[2]) if best else None


def trade_date_of(settle: date) -> date:
    """Fails files are dated by settlement; the trade was T+n trading days earlier."""
    lag = next(n for until, n in SETTLEMENT_LAG if settle < until)
    d = settle
    for _ in range(lag):
        d = previous_trading_day(d)
    return d


def by_symbol(ftd: dict) -> dict[str, list[tuple[date, date, str]]]:
    out: dict[str, list] = defaultdict(list)
    for c, pairs in ftd.items():
        for sym, first, last, _ in pairs:
            out[key(sym)].append((first, last, c))
    return out


def nearest_symbol(pairs: list, d: date) -> tuple[str, date] | None:
    """Fallback when no pair is inside the window: the closest one at any distance."""
    if not pairs:
        return None
    sym, first, last, _ = min(pairs, key=lambda p: min(abs((d - p[1]).days), abs((d - p[2]).days)))
    return sym, first


def load_fund_lists():
    """period -> fund -> {cusip: (name, isin, line_no)} for equity lines with a CUSIP."""
    lists: dict[date, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    no_cusip = Counter()
    for r in csv.DictReader((SEC / "nport_holdings.csv").open()):
        if r["asset_cat"] != "EC":
            continue
        c = r["cusip_resolved"].strip()
        if (not c or set(c) <= {"0"}) and r["isin"].strip() in ISIN_TICKER \
                and date.fromisoformat(r["report_period_end"]) < ISIN_TICKER[r["isin"].strip()][1]:
            c = r["isin"].strip()
        if not c or set(c) <= {"0"}:
            no_cusip[(r["fund"], r["name"])] += 1
            continue
        lists[date.fromisoformat(r["report_period_end"])][r["fund"]][c] = (
            r["name"], r["isin"], int(r["line_no"]), r["lei"].strip())
    return lists, no_cusip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="build and check; write nothing")
    ap.add_argument("--dsn", default=os.environ.get("USMARKET_DSN") or DEFAULT_DSN)
    args = ap.parse_args()

    changes, skipped = load_changes()
    ftd = load_ftd()
    lists, no_cusip = load_fund_lists()
    log(f"S&P changes: {len(changes)} dated, {len(skipped)} not usable (no date, no ticker, or not 'ok')")
    log(f"fund lists: {sum(len(v) for v in lists.values())} across {len(lists)} month-ends; "
        f"{len(no_cusip)} equity lines without any CUSIP skipped (CVRs)")

    # Display form: S&P's own spelling where S&P printed the ticker, else the SEC's.
    display: dict[str, str] = {"BRKB": "BRK.B", "BFB": "BF.B"}
    for c in sorted(changes, key=lambda c: c.effective):
        if c.symbol.upper() in NASDAQ_WHEN_ISSUED:
            continue
        if "." in c.symbol or key(c.symbol) not in display:
            display[key(c.symbol)] = re.sub(r"wi$", "", c.symbol)

    # 1. Checkpoints: per month-end, the securities a majority of filing funds held, by ticker.
    checkpoints = {}
    for p in sorted(lists):
        funds = lists[p]
        votes = Counter(c for f in funds.values() for c in f)
        need = len(funds) // 2 + 1
        names = {c: n for f in funds.values() for c, n in f.items()}
        tick, unnamed = {}, []
        for c in votes:
            # name the holding as of the day its composition takes effect (the next trading day)
            hit = symbol_at(ftd.get(c, []), next_trading_day(p)) or nearest_symbol(ftd.get(c, []), p)
            if c in ISIN_TICKER:
                hit = (ISIN_TICKER[c][0], p)
            if hit:
                tick[c] = key(hit[0])
            else:
                unnamed.append(c)
        held = {c for c, v in votes.items() if v >= need}
        checkpoints[p] = {
            "funds": sorted(funds), "cusips": held, "names": names, "votes": votes, "tick": tick,
            "keys": {tick.get(c, "CUSIP:" + c) for c in held},
            "disputed": sorted(tick.get(c, "CUSIP:" + c) for c, v in votes.items() if v < need),
            "unnamed": unnamed,
            # identities that survive a rename: CUSIP, ISIN, LEI
            "ids": {c: {c, *(x for f in funds.values() if c in f for x in (f[c][1], f[c][3]) if x and x != "N/A")}
                    for c in votes},
        }

    # 2. Ticker changes of continuing members. Between two consecutive month-ends, a ticker
    #    that disappeared and one that appeared are the same security when they share a
    #    CUSIP, ISIN or LEI (a rename often brings a new CUSIP; the LEI stays). Dated by the
    #    SEC's first sighting of the new ticker inside the gap.
    renames: dict[date, list[tuple[str, str, str, str]]] = defaultdict(list)   # eff -> (old, new, cusip, note)
    periods = sorted(checkpoints)
    seen_rename = set()
    for a, b in zip(periods, periods[1:]):
        A, B = checkpoints[a], checkpoints[b]
        a_by_key = defaultdict(set)
        for c, k in A["tick"].items():
            a_by_key[k] |= A["ids"][c]
        b_by_key = defaultdict(set)
        for c, k in B["tick"].items():
            b_by_key[k] |= B["ids"][c]
        gone = {k: ids for k, ids in a_by_key.items() if k not in b_by_key}
        came = {k: ids for k, ids in b_by_key.items() if k not in a_by_key}
        for old, ids_a in gone.items():
            for new, ids_b in came.items():
                shared = ids_a & ids_b
                if not shared or (old, new) in seen_rename:
                    continue
                seen_rename.add((old, new))
                b_cusips = [c for c, k in B["tick"].items() if k == new]
                first = min((f for c in b_cusips for s_, f, _, _ in ftd.get(c, []) if key(s_) == new),
                            default=None)
                dated = bool(first and a < first <= b + timedelta(days=FTD_WINDOW))
                when = on_or_after(first) if dated else next_trading_day(a)
                renames[min(when, next_trading_day(b))].append(
                    (old, new, b_cusips[0],
                     f"{old} at {a} and {new} at {b} share {sorted(shared)[0]}; "
                     + (f"SEC fails data first shows {new} on {first}" if dated
                        else "no SEC date inside the gap: placed at the start of the gap")))
                break

    sym_ftd = by_symbol(ftd)

    def first_trade(sym: str, after: date | None) -> date | None:
        """First trade under a ticker on or after `after` (None if the SEC data never shows it)."""
        firsts = [f for f, _, _ in sym_ftd.get(key(sym), []) if after is None or f >= after]
        return on_or_after(min(firsts)) if firsts else None

    def delisted_after(sym: str, ann: date) -> date | None:
        """Last trade under a ticker, only if it stopped trading within a year of `ann`."""
        # Per CUSIP sighting, since tickers are reused (CEG again from 2022): the sighting that
        # was trading at the announcement and ended within a year. Its last fail can predate
        # the announcement by days, because S&P announces deal closings late.
        ends = sorted(l for f, l, _ in sym_ftd.get(key(sym), [])
                      if f < ann and ann - timedelta(days=30) <= l <= ann + timedelta(days=365))
        return max(trade_date_of(ends[0]), previous_trading_day(ann)) if ends else None

    # 3a0. Before Sep 2019 there are no fund lists to find ticker changes; the SEC fails data
    #      finds them directly: one CUSIP whose ticker changed, dated by the new ticker's first
    #      sighting. Conditional like every rename: it touches the index only for a member.
    first_list = min(checkpoints)
    plain = re.compile(r"^[A-Z]{1,5}$")
    have = {(o, n) for rs in renames.values() for o, n, _, _ in rs}
    for c, pairs in ftd.items():
        seq = sorted((f, l, key(sym)) for sym, f, l, _ in pairs if plain.match(key(sym)))
        for (f1, l1, old), (f2, l2, new) in zip(seq, seq[1:]):
            if old == new or not (START <= f2 < first_list) or (old, new) in have:
                continue
            if not (f1 < f2 and l2 >= l1):           # the new ticker must succeed the old one
                continue
            if new in (old + "D", old + "E") or old in (new + "D", new + "E"):
                continue                             # temporary 5th letter: D reverse split, E late filer
            when, how = RENAME_DATE.get((old, new), (on_or_after(f2), ""))
            renames[when].append((old, new, c, f"CUSIP {c} traded as {old} until {l1} and "
                                                          f"as {new} from {f2} (SEC fails data)" + (f"; dated {when}: {how}" if how else "")))
            have.add((old, new))

    # 3a. Ticker changes S&P announced. Its date when S&P gave one; else the first trade under
    #     the new ticker after the announcement. A rename the fund lists already found is kept
    #     once, with the fund-list date.
    unusable = []
    for r in csv.DictReader(TICKER_CHANGES.open()):
        old, new = key(r["old_symbol"]), key(r["new_symbol"])
        if not old or not new or (old, new) in have:
            continue
        ann = date.fromisoformat(r["announced_date"])
        if r["effective_date"]:
            when, how = date.fromisoformat(r["effective_date"]), "S&P's date"
        else:
            t = first_trade(new, ann - timedelta(days=30))
            if not t:
                unusable.append(f"ticker change {old}->{new} announced {ann}: no date in S&P's text or SEC data")
                continue
            when, how = on_or_after(t), f"first trade as {new} in SEC fails data"
        renames[when].append((old, new, "", f"S&P announced {ann} ({r['release_url']}); dated by {how}"))
        have.add((old, new))

    # 3b. S&P's "date to be announced" changes, dated by the SEC data: the first trade of a new
    #     ticker the release names, else the day after the deleted company's last trade.
    tbd = defaultdict(list)
    for r in skipped:
        if r["status"] == "date_tbd" and r["symbol"]:
            tbd[r["release_url"]].append(r)
    extra = []
    for url, rows in tbd.items():
        ann = date.fromisoformat(rows[0]["announced_date"])
        when, how = None, ""
        for r in rows:
            if r["action"] == "include":
                t = first_trade(r["symbol"], None)        # a ticker first seen after the announcement is new
                if t and t > ann - timedelta(days=30):
                    when, how = on_or_after(t), f"first trade as {r['symbol']}"
        if not when:
            for r in rows:
                if r["action"] == "exclude":
                    trig, why = TBD_TRIGGER.get(key(r["symbol"]), (r["symbol"], ""))
                    t = delisted_after(trig, ann)
                    if t:
                        when = next_trading_day(t)
                        how = f"day after {trig}'s last trade" + (f"; {why} (general knowledge)" if why else "")
                        break
        if not when:
            unusable += [f"date_tbd {r['action']} {r['symbol']} announced {ann}: no SEC date" for r in rows]
            continue
        for r in rows:
            extra.append(Change(when, r["action"], r["symbol"].strip(), r["company"], ann, url,
                                f"S&P: date to be announced; dated by SEC fails data ({how}). {r['note'][:300]}"))

    # 3c. Replacements with no S&P press release, dated by the new ticker's first trade.
    def paired(old: str, new: str) -> date | None:
        """The new ticker's first sighting within 10 days of the old one's last (reused tickers
        such as SII and LIN make 'first' and 'last' of a ticker alone ambiguous)."""
        hits = sorted(f for _, l, _ in sym_ftd.get(old, []) for f, _, _ in sym_ftd.get(new, [])
                      if abs((f - l).days) <= 10)
        return on_or_after(hits[0]) if hits else None

    for old, new, what, by in NO_RELEASE_REPLACEMENTS:
        if by == "old_last":     # the old company's sighting that was trading when the stretch began
            ends = sorted(l for f, l, _ in sym_ftd.get(old, []) if f <= START + timedelta(days=365))
            t = next_trading_day(trade_date_of(ends[0])) if ends else None
        else:
            t = paired(old, new) or first_trade(new, None)
        if not t:
            unusable.append(f"replacement {old}->{new}: no SEC date")
            continue
        extra += [Change(on_or_after(t), "exclude", old, what, None, "", f"No S&P press release found; {what}; "
                         f"dated by SEC fails data ({'day after ' + old + ' last traded' if by == 'old_last' else 'first trade as ' + new})"),
                  Change(on_or_after(t), "include", new, what, None, "", f"No S&P press release found; {what}; "
                         f"dated by SEC fails data ({'day after ' + old + ' last traded' if by == 'old_last' else 'first trade as ' + new})")]
    for old, new, what in NO_RELEASE_RENAMES:
        # the old ticker's last sighting and the new one's first, within 10 days of each other
        # (tickers are reused later: ACT by Enact in 2021, Q by Qnity in 2025)
        t = RENAME_DATE.get((old, new), (None,))[0] or paired(old, new)
        if not t:
            unusable.append(f"rename {old}->{new}: new ticker not in SEC data")
            continue
        renames[t].append((old, new, "", f"No S&P press release found; {what}; dated by SEC fails data "
                                         f"(first trade as {new})"))
    for action, sym, what in NO_RELEASE_LINES:
        if action == "include":
            t = first_trade(sym, None)
        else:
            last = max((l for _, l, _ in sym_ftd.get(sym, [])), default=None)
            t = next_trading_day(trade_date_of(last)) if last else None
        if not t:
            unusable.append(f"{action} {sym}: not in SEC data")
            continue
        extra.append(Change(t, action, sym, what, None, "", f"No S&P press release found; {what}; dated by "
                            f"SEC fails data ({'first sighting' if action == 'include' else 'day after last trade'})"))
    changes = changes + extra

    # A rename the fund lists found gives way when S&P itself adds the new ticker around
    # that date (Discovery -> WBD). It stays when S&P only names the old ticker later
    # (FBHS -> FBIN, which S&P then deleted as FBHS): that is read through the rename below.
    sp_adds = defaultdict(list)
    for c in changes:
        if c.action == "include":
            sp_adds[key(c.symbol)].append(c.effective)
    dropped = []
    for d in list(renames):
        keep = []
        for r in renames[d]:
            o, n, _, note = r
            near = [x for x in sp_adds[n] if abs((x - d).days) <= 10]
            if near and not note.startswith("S&P"):
                dropped.append(f"{o}->{n} {d}: S&P adds {n} itself on {min(near)}")
            else:
                keep.append(r)
        renames[d] = keep
    log(f"detected renames dropped because S&P adds the new ticker itself: {dropped}")
    # 3d. S&P sometimes names a member by a ticker it changed shortly before (FBHS after it
    #     became FBIN; GDI after it became IR). Within 90 days of a rename, read the old
    #     ticker as the new one. One hop only: a ticker reused by another company is not followed.
    rename_list = sorted((d, o, n) for d, rs in renames.items() for o, n, _, _ in rs)

    def resolve(k: str, d: date) -> tuple[str, str | None]:
        for rd, o, n in reversed(rename_list):
            if o == k and rd <= d <= rd + timedelta(days=90):
                return n, f"S&P's {k} read as {n} (renamed {rd})"
        return k, None

    # 3e. One step per effective date: S&P's excludes, then includes, then ticker changes.
    steps: dict[date, list[tuple]] = defaultdict(list)
    aliased = []
    for c in sorted(changes, key=lambda c: (c.effective, c.action != "exclude")):
        k, why = resolve(key(c.symbol), c.effective)
        if why:
            aliased.append((c.effective, why))
            # S&P's change on the rename's own day already carries the new ticker: drop the rename
            renames[c.effective] = [r for r in renames.get(c.effective, [])
                                    if not (r[0] == key(c.symbol) and r[1] == k)]
        steps[c.effective].append((c.action, k, None))
    for d, rs in renames.items():
        rs[:] = [r for r in rs if r]
        pairs = [(o, n) for o, n, _, _ in rs]
        # a rename whose old ticker another rename takes goes first (IR->TT before GDI->IR)
        pairs.sort(key=lambda on: 0 if any(n2 == on[0] for _, n2 in pairs) else 1)
        steps[d] += [("rename", o, n) for o, n in pairs]
    # Within a day: deletions free tickers, renames move them, then additions take them.
    order = {"exclude": 0, "rename": 1, "include": 2}
    for d in steps:
        steps[d].sort(key=lambda st: order[st[0]])
    dates = sorted(steps)
    log(f"dated from SEC data: {len(extra)} change rows; S&P tickers read through a rename: {len(aliased)}; "
        f"unusable: {len(unusable)}")
    for u in unusable:
        log(f"   unusable: {u}")

    def apply(m: set, d: date, forward: bool) -> list[str]:
        """One day's steps. A rename touches the index only if the security is a member."""
        bad = []
        for op, k, new in (steps[d] if forward else reversed(steps[d])):
            if op == "rename":
                src, dst = (k, new) if forward else (new, k)
                if src in m:
                    if dst in m:
                        bad.append(f"rename {k}->{new}: {dst} already a member")
                    m.discard(src)
                    m.add(dst)
            elif (op == "include") == forward:
                if k in m:
                    bad.append(f"{op}:{k} already a member")
                m.add(k)
            else:
                if k not in m:
                    bad.append(f"{op}:{k} not a member")
                m.discard(k)
        return bad

    # 4. Roll from the anchor. The anchor list is dated at a close, so it is the composition
    #    effective on the next trading day.
    anchor = checkpoints[ANCHOR_PERIOD]
    assert set(anchor["funds"]) == set(ANCHOR_FUNDS), anchor["funds"]
    a_eff = next_trading_day(ANCHOR_PERIOD)
    base = set(anchor["keys"])
    snaps: dict[date, frozenset] = {}
    contradictions = []
    m = set(base)
    # state effective on a_eff includes every step dated <= a_eff
    snaps[a_eff] = frozenset(m)
    for d in [d for d in dates if d > a_eff]:
        contradictions += [(d, "roll_forward", x) for x in apply(m, d, True)]
        snaps[d] = frozenset(m)
    m = set(base)
    back = [d for d in dates if START < d <= a_eff][::-1]
    for i, d in enumerate(back):
        contradictions += [(d, "roll_backward", x) for x in apply(m, d, False)]
        prev = back[i + 1] if i + 1 < len(back) else START
        snaps[prev] = frozenset(m)
    # Keep a snapshot only where the membership changed (most SEC-found renames touch no member).
    kept, last = {}, None
    for d in sorted(snaps):
        if snaps[d] != last:
            kept[d] = last = snaps[d]
    snaps = kept

    def state_on(d: date) -> frozenset:
        return snaps[max(x for x in snaps if x <= d)]

    # 5. Compare with every fund month-end.
    results = []
    for p in periods:
        cp = checkpoints[p]
        roll = state_on(next_trading_day(p))
        missing = sorted(cp["keys"] - roll)     # funds hold, roll lacks
        extra = sorted(roll - cp["keys"])       # roll has, funds lack
        cp["excused"] = []
        if len(cp["funds"]) == 1 and cp["funds"][0] in FUND_KNOWN_OMISSIONS:
            lines, since, why = FUND_KNOWN_OMISSIONS[cp["funds"][0]]
            if p >= since:
                cp["excused"] = [k for k in extra if k in lines]
                extra = [k for k in extra if k not in lines]
        results.append((p, cp, missing, extra))

    # 6. Every member before the fund lists should trade under its ticker near the date: the SEC
    #    fails data shows it within 120 days. A miss means a ticker change was not undone.
    sightings = defaultdict(list)
    for c, pairs in ftd.items():
        for sym, f, l, _ in pairs:
            sightings[key(sym)].append((f, l))
    unseen = defaultdict(list)
    for d, m in snaps.items():
        if d >= next_trading_day(min(checkpoints)):
            continue
        for k in m:
            if not any(f - timedelta(days=120) <= d <= l + timedelta(days=120) for f, l in sightings.get(k, [])):
                unseen[k].append(d)
    sighting_checks = [(min(ds), k, len(ds), max(ds)) for k, ds in unseen.items()]
    log(f"members before Sep 2019 with no SEC sighting within 120 days: "
        f"{[(k, str(a), str(b)) for a, k, n, b in sighting_checks]}")

    # 7. Before Sep 2019 the funds' N-CSR/N-Q schedules give names only. Name each holding and
    #    compare it with the roll exactly as build_sp500_2003_2009.py does for 2003-2009.
    name_results, name_confirmed, name_suspects, name_lists, name_explained = [], set(), [], {}, set()
    if NAME_SUMMARY.exists() and NAME_HOLDINGS.exists():
        import build_sp500_2003_2009 as names_check  # noqa: PLC0415
        name_lists = names_check.load_fund_lists(NAME_SUMMARY, NAME_HOLDINGS)
        # the Dec 2009 lists close the stretch before the first 2010 list
        name_lists.update({fp: v for fp, v in names_check.load_fund_lists().items() if fp[1] >= date(2009, 12, 31)
                           and fp not in name_lists})
        named_ids = names_check.load_ftd_names()
        known = defaultdict(set)
        for c in changes:
            known[key(c.symbol)].add(c.company)
        dated = [(key(r["new_symbol"]), r["old_company"], date.fromisoformat(r["effective_date"]) - timedelta(days=10),
                  date.fromisoformat(r["effective_date"]) + timedelta(days=names_check.NAME_WINDOW))
                 for r in csv.DictReader(TICKER_CHANGES.open())
                 if r["new_symbol"] and r["old_company"] and r["effective_date"]]
        namer = names_check.Namer(named_ids, known, dated, rename_list)
        for fund, p in sorted((fp for fp in name_lists if START <= next_trading_day(fp[1]) and fp[1] < first_list),
                              key=lambda fp: (fp[1], fp[0])):
            eff = next_trading_day(p)
            got = names_check.check_list(namer, name_lists[(fund, p)], state_on(eff), eff)
            name_results.append((p, fund, len(name_lists[(fund, p)]), *got))
        name_confirmed, name_suspects, name_explained = names_check.classify(name_results, steps, rename_list)
        log(f"name-only fund lists {START}..{first_list}: {sum(1 for r in name_results if not r[4] and not r[5] and not r[6])} "
            f"of {len(name_results)} exact; month-ends confirmed {len(name_confirmed)} of {len({r[0] for r in name_results})}; "
            f"cross-fund suspects {name_suspects}")

    # The NPORT month-ends get the same status as the name-only ones (confirmed / explained /
    # unexplained), from the same labelling of each difference.
    import build_sp500_2003_2009 as names_check  # noqa: PLC0415
    np_results = [(p, "+".join(cp["funds"]), len(cp["keys"]), {}, dict(enumerate(mi)), list(ex), [], [])
                  for p, cp, mi, ex in results]
    np_confirmed, np_suspects, np_explained = names_check.classify(np_results, steps, rename_list)

    ok = sum(1 for _, _, mi, ex in results if not mi and not ex)
    log(f"anchor {ANCHOR_PERIOD} ({'+'.join(anchor['funds'])}): {len(base)} securities, effective {a_eff}")
    log(f"ticker changes found from CUSIPs: {sum(len(v) for v in renames.values())}")
    log(f"snapshots: {len(snaps)} from {min(snaps)} to {max(snaps)}; contradictions in the roll: {len(contradictions)}")
    for c in contradictions[:30]:
        log(f"   {c[1]:<14} {c[0]}  {c[2]}")
    log(f"fund month-ends matching the roll exactly: {ok} of {len(results)}")
    for p, cp, mi, ex in results:
        if mi or ex:
            log(f"   {p} {'+'.join(cp['funds']):<16} funds-only {mi}  roll-only {ex}")
    counts = Counter(len(s) for s in snaps.values())
    log(f"snapshot sizes: {dict(sorted(counts.items()))}")

    if args.dry_run:
        log("dry run: nothing written")
        return 0
    return write(args.dsn, changes, checkpoints, renames, snaps, results, contradictions, display, a_eff,
                 sighting_checks, name_results, name_confirmed, name_suspects, name_lists, name_explained,
                 np_results, np_confirmed, np_explained)


def write(dsn, changes, checkpoints, renames, snaps, results, contradictions, display, a_eff,
          sighting_checks, name_results=(), name_confirmed=frozenset(), name_suspects=(), name_lists=None,
          name_explained=frozenset(), np_results=(), np_confirmed=frozenset(), np_explained=frozenset()) -> int:
    import psycopg2  # noqa: PLC0415
    from psycopg2.extras import execute_values  # noqa: PLC0415

    show = lambda k: display.get(k, k)  # noqa: E731
    periods = sorted(checkpoints)
    eff = {p: next_trading_day(p) for p in periods}
    matched = {p for p, _, mi, ex in results if not mi and not ex}

    # A snapshot is verified when the checkpoints on both sides of it agree with the roll.
    # A month-end agrees when it is confirmed or explained (every difference a recorded fund-side
    # cause, and no cross-fund suspect); month_end_status in the reconciliation keeps which.
    np_ok = set(np_confirmed) | set(np_explained)
    cps = {eff[p]: p in np_ok for p in periods}
    for p in {r[0] for r in name_results}:
        cps[next_trading_day(p)] = (p in name_confirmed or p in name_explained) and not name_suspects
    cp_days = sorted(cps)

    def verified(d: date) -> bool:
        before = [x for x in cp_days if x <= d]
        after = [x for x in cp_days if x > d]
        return bool(before and after and cps[before[-1]] and cps[after[0]])

    own = [s[0] for s in SOURCES]
    covered_through = date.today()
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute((HERE / "schema.sql").read_text())
        for t, where in (("index_membership", "effective_date >= '2010-01-01'"),
                         ("index_membership_coverage", "covered_from >= '2010-01-01'"),
                         ("index_membership_reconciliation", "check_date >= '2010-01-01'"),
                         ("index_change_event", "source = any(%(own)s)"),
                         ("index_symbol_change", "source = any(%(own)s)"),
                         ("index_constituent_list", "source = any(%(own)s)")):
            cur.execute(f"delete from usmarket.{t} where index_type = %(ix)s and {where}", {"ix": INDEX, "own": own})
        cur.execute("truncate usmarket.sec_cusip_symbol")
        execute_values(cur, """insert into usmarket.index_source_file
            (source, publisher, kind, path, url, captured_on, note) values %s
            on conflict (source) do update set publisher = excluded.publisher, kind = excluded.kind,
              path = excluded.path, url = excluded.url, captured_on = excluded.captured_on, note = excluded.note""",
            SOURCES)

        ev, seen = [], set()
        for c in changes:
            row = (INDEX, previous_trading_day(c.effective), c.effective, c.action, show(key(c.symbol)))
            if row in seen:
                continue
            seen.add(row)
            ev.append((*row, c.company or "?", SOURCE_PRESS if c.url else SOURCE_FTD, c.note[:2000] or None,
                       c.announced, c.url or None))
        execute_values(cur, """insert into usmarket.index_change_event
            (index_type, after_close_date, effective_date, action, symbol, company, source, note,
             announced_date, release_url) values %s""", ev)

        execute_values(cur, """insert into usmarket.index_symbol_change
            (index_type, effective_date, old_symbol, new_symbol, company, source, note, cusip) values %s
            on conflict do nothing""",
            [(INDEX, d, show(o), show(n), "", SOURCE_PRESS if note.startswith("S&P") else
              SOURCE_FTD if "SEC fails data" in note and not note.startswith("No S&P") else SOURCE_FUNDS,
              note[:2000], c or None)
             for d, rs in renames.items() for o, n, c, note in rs
             if o in snaps[max((x for x in snaps if x < d), default=min(snaps))]])   # renames of members only

        rows, line = [], 0
        for p in periods:
            cp = checkpoints[p]
            need = len(cp["funds"]) // 2 + 1
            basis = f"Fund holdings at {p} close ({'+'.join(cp['funds'])}); member list = held by >= {need}"
            for c, v in sorted(cp["votes"].items()):
                line += 1
                rows.append((SOURCE_FUNDS, line, INDEX, p, basis, show(cp["tick"].get(c, "")) or None,
                             cp["names"][c][0], None, c if len(c) == 9 else None, cp["names"][c][1] or None, v))
        own_names = [r for r in name_results if r[0] >= date(2010, 1, 1)]   # Dec 2009 is the 2003-2009 build's
        for p, fund, n, named, *_ in own_names:
            basis = f"{fund} holdings at {p} close (SEC N-CSR/N-Q); names matched to tickers via SEC fails data"
            for ln, name, section in name_lists[(fund, p)]:
                line += 1
                rows.append((SOURCE_NAMES, line, INDEX, p, basis, show(named[ln]) if ln in named else None,
                             name, section, None, None, 1))
        execute_values(cur, """insert into usmarket.index_constituent_list
            (source, line_no, index_type, as_of_date, as_of_basis, symbol, company, industry, cusip, isin,
             fund_count) values %s""", rows, page_size=5000)

        mrows = []
        for d, m in snaps.items():
            v = verified(d)
            mrows += [(INDEX, d, show(k), "sp_press_2010_2026:roll_from_sec_nport_2026-06-30", v) for k in sorted(m)]
        execute_values(cur, """insert into usmarket.index_membership
            (index_type, effective_date, symbol, source, is_verified) values %s""", mrows, page_size=5000)

        first_cp = eff[periods[0]]
        execute_values(cur, "insert into usmarket.index_membership_coverage values %s", [
            (INDEX, min(snaps), previous_trading_day(first_cp),
             f"S&P press releases rolled back from the Sep 2019 fund lists; checked against index funds' N-CSR/N-Q "
             f"holdings by name at {len({r[0] for r in name_results})} month-ends, {len(name_confirmed)} confirmed"
             if name_results else
             "S&P press releases rolled back from the Sep 2019 fund lists; no fund list checks it (unverified)"),
            (INDEX, first_cp, covered_through,
             "S&P press releases, checked against fund holdings at every month-end Sep 2019 to Jul 2026"),
        ])

        recon = []
        for p, cp, mi, ex in results:
            recon.append((INDEX, "fund_month_end", p, not mi and not ex, len(cp["keys"]), len(cp["keys"]) + len(ex) - len(mi),
                          [show(k) for k in mi], [show(k) for k in ex],
                          f"Funds {'+'.join(cp['funds'])} at {p} close vs the roll effective {eff[p]}. "
                          f"missing = funds hold, roll lacks; extra = roll has, funds lack. "
                          + (f"Excused, a known fund omission: {[show(k) for k in cp['excused']]} "
                             f"({FUND_KNOWN_OMISSIONS[cp['funds'][0]][2]}). " if cp["excused"] else "")
                          + (f"Held by a minority of funds only: {[show(k) for k in cp['disputed']]}" if cp["disputed"] else "")))
        grouped = defaultdict(list)
        for d, kind, msg in contradictions:
            grouped[(kind, d)].append(msg)
        recon += [(INDEX, kind, d, False, None, None, [], [], "; ".join(msgs)) for (kind, d), msgs in grouped.items()]
        by_day = defaultdict(list)
        for first, k, n, last in sighting_checks:
            by_day[first].append(f"{show(k)} in {n} snapshots to {last}")
        recon += [(INDEX, "sec_sighting", d, False, None, None, [], [],
                   "Member with no SEC fails-data sighting within 120 days (a ticker change not undone?): "
                   + "; ".join(v)) for d, v in by_day.items()]
        for p, fund, n, named, missing, extra, unnamed, notes in own_names:
            recon.append((INDEX, f"fund_month_end_{fund}", p, not missing and not extra and not unnamed, n,
                          n - len(missing) - len(unnamed) + len(extra), [show(t) for t in missing.values()],
                          [show(k) for k in extra],
                          f"{fund} at {p} close (by name) vs the roll effective {next_trading_day(p)}; "
                          f"{'month-end confirmed' if p in name_confirmed else 'month-end not confirmed'}. "
                          + (f"Fund lines naming no ticker: {[x[1] for x in unnamed]}. " if unnamed else "")
                          + (f"Explained: {notes}" if notes else "")))
        import build_sp500_2003_2009 as names_check  # noqa: PLC0415
        recon += [(r[0], "month_end_status_nport", *r[2:]) for r in
                  names_check.month_end_status(INDEX, np_results, np_confirmed, np_explained)]
        if name_results:
            recon += names_check.month_end_status(INDEX, own_names, name_confirmed, name_explained)
            recon.append((INDEX, "cross_fund_suspects", date(2019, 8, 30), not name_suspects, 0, len(name_suspects),
                          [], [], "Members no fund list held within 45 days, and non-members every fund list held, "
                          "2010-2019 (by name): " + ("; ".join(f"{d}: {m}" for d, m in name_suspects)
                                                     if name_suspects else "none")))
        execute_values(cur, """insert into usmarket.index_membership_reconciliation
            (index_type, check_name, check_date, reconciled, expected, actual, missing, extra, note) values %s""", recon)

        # 2009-07 onward, plus Mar 2004 - Jun 2009 when fetched (fetch_sec_holdings.py --ftd-from 2004-03);
        # a pair seen in both keeps its first and last sighting across them.
        merged: dict[tuple[str, str], dict] = {}
        for f in ("ftd_cusip_symbol_2004_2009.csv", "ftd_cusip_symbol.csv"):
            if (SEC / f).exists():
                for r in csv.DictReader((SEC / f).open()):
                    k = (r["cusip"], r["symbol"])
                    if k in merged:
                        r = {**r, "first_seen": min(r["first_seen"], merged[k]["first_seen"]),
                             "last_seen": max(r["last_seen"], merged[k]["last_seen"])}
                    merged[k] = r
        pairs = list(merged.values())
        execute_values(cur, """insert into usmarket.sec_cusip_symbol
            (cusip, symbol, description, first_seen, last_seen, placeholder) values %s on conflict do nothing""",
            [(r["cusip"].replace("\x00", ""), r["symbol"].replace("\x00", ""),
              r["description"].replace("\x00", ""),       # five SEC rows carry a NUL byte
              r["first_seen"], r["last_seen"], r["placeholder"] == "Y")
             for r in pairs], page_size=10000)
    log(f"wrote {len(mrows)} membership rows ({sum(r[4] for r in mrows)} verified), {len(ev)} change rows, "
        f"{sum(len(v) for v in renames.values())} ticker changes, {len(rows)} fund-list rows, "
        f"{len(recon)} checks, {len(pairs)} CUSIP-ticker pairs, {len(name_results)} name-only fund lists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
