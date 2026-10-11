#!/usr/bin/env python3
"""Point-in-time S&P 500 membership from S&P's own files, into schema usmarket.

THE SOURCES (all in this repo, captured from S&P's old site via the Wayback Machine)
-----------
* S&P's yearly change lists for 1999, 2000, 2001 and 2002 (to 18 Nov), every row
  "effective after close of trading" with the added and deleted tickers.
* S&P's full constituent file ``500alpha.csv``. It was captured from Feb 2002 to
  Jan 2003 but was not kept current, so its as-of date is found here from the
  change lists rather than taken from the capture date.
* SPDR Trust's annual report (SEC N-30D) for 30 Sep 2001: a fund's list, names only.
  Used as a cross-check, never as a checkpoint (RESEARCH.md, decision 1).

THE METHOD (``market-pulse/backtesting/backend/universe/build_event_membership.py``)
----------
1. Find the change date at which 500alpha.csv holds: the cut where rolling the
   change lists backward and forward from it contradicts the least.
2. Roll S&P's changes back to the first trading day of 1999 and forward to the
   last change, writing one full snapshot per change date.
3. Record every contradiction (a delete of a non-member, an add of a member) and
   every member count other than 500 in index_membership_reconciliation.
   Nothing is smoothed or guessed: a contradiction stays in the data and the table.

Only the 500alpha.csv snapshot is is_verified. The rest follow from S&P's own
notices but are not closed by a second S&P list, so they are not marked verified.

Usage:
    python3 sp500_history/membership/build_sp500_membership.py --dry-run
    python3 sp500_history/membership/build_sp500_membership.py
"""
from __future__ import annotations

import argparse
import csv
import difflib
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_DSN = "postgresql://abhrajitpal@127.0.0.1:5434/market_pulse"
INDEX = "SP500"
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OLD = "sp500_history/research_a/wayback/spglobal_old"

# NYSE weekday closures 1999-2003. Checked against Yahoo's ^GSPC trading days
# (research_c/yahoo_gspc/gspc.json, not in git): identical, incl. 11-14 Sep 2001.
NYSE_CLOSED = {date.fromisoformat(d) for d in """
1999-01-01 1999-01-18 1999-02-15 1999-04-02 1999-05-31 1999-07-05 1999-09-06 1999-11-25 1999-12-24
2000-01-17 2000-02-21 2000-04-21 2000-05-29 2000-07-04 2000-09-04 2000-11-23 2000-12-25
2001-01-01 2001-01-15 2001-02-19 2001-04-13 2001-05-28 2001-07-04 2001-09-03 2001-09-11
2001-09-12 2001-09-13 2001-09-14 2001-11-22 2001-12-25 2002-01-01 2002-01-21 2002-02-18
2002-03-29 2002-05-27 2002-07-04 2002-09-02 2002-11-28 2002-12-25 2003-01-01 2003-01-20
2003-02-17 2003-04-18 2003-05-26 2003-07-04 2003-09-01 2003-11-27 2003-12-25""".split()}

SOURCES = [
    # source, publisher, kind, path, url, captured_on, note
    ("sp_changes_1999", "S&P", "change_list",
     f"{OLD}/ssindexmain500indchange1999.html_20001010051523.txt",
     "https://web.archive.org/web/20001010051523/http://www.spglobal.com/ssindexmain500indchange1999.html",
     "2000-10-10", "Full year 1999"),
    ("sp_changes_2000", "S&P", "change_list",
     f"{OLD}/indexmain500_changes00.html_20021031132956.txt",
     "https://web.archive.org/web/20021031132956/http://www.spglobal.com/indexmain500_changes00.html",
     "2002-10-31", "Full year 2000"),
    ("sp_changes_2001", "S&P", "change_list",
     f"{OLD}/indexmain500_changes01.html_20021216175519.txt",
     "https://web.archive.org/web/20021216175519/http://www.spglobal.com/indexmain500_changes01.html",
     "2002-12-16", "Full year 2001"),
    ("sp_changes_2002", "S&P", "change_list",
     f"{OLD}/indexmain500_changes.html_20021201121110.txt",
     "https://web.archive.org/web/20021201121110/http://www.spglobal.com/indexmain500_changes.html",
     "2002-12-01", "2002 to 18 Nov; December not captured"),
    ("sp_500alpha", "S&P", "constituent_list", f"{OLD}/500alpha.csv",
     "http://www.spglobal.com/500alpha.csv", "2002-02-01",
     "Byte-identical Feb 2002 to Jan 2003 captures; as-of date inferred from the change lists"),
    ("spdr_n30d_20010930", "SPDR Trust Series 1 (SEC N-30D, CIK 884394)", "fund_holdings",
     "sp500_history/sp500probe/spy2001.txt", None, None,
     "Annual report, holdings at 30 Sep 2001; names only"),
]
YEAR_OF = {"sp_changes_1999": 1999, "sp_changes_2000": 2000, "sp_changes_2001": 2001, "sp_changes_2002": 2002}

# Ticker changes for continuing members. Without them a reused ticker (JPM, HON, USB,
# ATI) reads as a member deleted and re-added. S&P dates three of them; the others are
# placed at the earliest change date the files allow, which moves only the label.
# Old tickers marked "(general knowledge)" are not printed in these files.
UNDATED = "Date not in S&P's text: placed at the earliest change date the files allow; membership unaffected. "
RENAMES = [
    # after_close_date, old, new, company, source, note
    (date(1999, 9, 28), "GBLX", "GX", "Global Crossing", "sp_500alpha",
     UNDATED + "Added as GBLX (S&P 1999 list); 500alpha.csv lists GX; deleted as GX 9 Oct 2001."),
    (date(1999, 6, 29), "ALT", "ATI", "Allegheny Technologies Inc.", "sp_500alpha",
     UNDATED + "ATI freed by AirTouch's deletion 29 Jun 1999; 500alpha.csv lists Allegheny Technologies "
     "as ATI. Old ticker ALT (Allegheny Teledyne) from general knowledge."),
    (date(1999, 11, 4), "PTVwi", "PTV", "Pactiv Corp.", "sp_changes_1999",
     "S&P 1999 note: Tenneco Packaging (PTVwi) \"name changed to Pactiv Corp.\"; when-issued to "
     "regular way; 500alpha.csv lists PTV. " + UNDATED),
    (date(1999, 12, 1), "ALD", "HON", "Honeywell International Inc.", "sp_changes_1999",
     "S&P 1999 note: \"AlliedSignal name change to Honeywell International Inc. (HON) after acquiring "
     "Honeywell\"; placed with Honeywell's deletion. Old ticker ALD from general knowledge."),
    (date(2000, 12, 29), "CMB", "JPM", "J.P. Morgan Chase & Co.", "sp_500alpha",
     "Not in S&P's change text: J.P. Morgan (JPM) deleted 29 Dec 2000, 500alpha.csv lists J.P. Morgan "
     "Chase as JPM; placed with the deletion. Old ticker CMB (Chase Manhattan) from general knowledge."),
    (date(2001, 2, 26), "FSR", "USB", "U.S. Bancorp", "sp_changes_2001",
     "S&P 2001 note: \"Firstar Corporation changed its name to U.S. Bancorp (USB) on 2/26/01\"; "
     "old U.S. Bancorp deleted the same day. Old ticker FSR from general knowledge."),
    (date(2001, 8, 31), "FTU", "WB", "Wachovia Corp. (was First Union)", "spdr_n30d_20010930",
     "Not in S&P's change text: old Wachovia (WB) deleted 31 Aug 2001; 500alpha.csv lists First Union "
     "as FTU and SPDR's 30 Sep 2001 list names it Wachovia Corp; placed with the deletion. "
     "New ticker WB from general knowledge."),
    (date(2001, 6, 22), "COC.B", "COC", "Conoco Inc.", "sp_500alpha",
     UNDATED + "Added as COC.B 6 Aug 1999 and listed so in 500alpha.csv; deleted as COC 30 Aug 2002."),
]


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


def next_trading_day(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5 or d in NYSE_CLOSED:
        d += timedelta(days=1)
    return d


def first_trading_day_on_or_after(d: date) -> date:
    return d if d.weekday() < 5 and d not in NYSE_CLOSED else next_trading_day(d)


@dataclass(frozen=True)
class Event:
    after_close: date
    action: str      # include | exclude
    symbol: str
    company: str
    source: str
    note: str | None

    @property
    def effective(self) -> date:
        return next_trading_day(self.after_close)


def blank(s: str) -> bool:
    return not s.strip("- ")


def parse_change_list(source: str, path: Path) -> list[Event]:
    """S&P's table, flattened to one cell per line: Date, Co, Ticker, Co, Ticker[, notes]."""
    toks = [t.strip() for t in path.read_text(errors="ignore").splitlines() if t.strip()]
    header = [i for i, t in enumerate(toks) if t == "Ticker"]
    toks = toks[header[1] + 1:]
    rows: list[list[str]] = []
    for t in toks:
        if re.fullmatch(r"\d{1,2}/\d{1,2}", t):
            rows.append([t])
        elif rows:
            rows[-1].append(t)
    out = []
    for r in rows:
        m, d = map(int, r[0].split("/"))
        when = date(YEAR_OF[source], m, d)
        add_co, add_sym, del_co, del_sym = (x.rstrip("*").strip() for x in r[1:5])
        # Page footnotes ("*Firstar ...", "Note: AlliedSignal ...") follow the last row but
        # belong to the page; they are carried by RENAMES instead.
        note = " ".join(x for x in r[5:]
                        if not x.startswith(("Copyright", "Send questions", "*", "Note:"))) or None
        if not blank(add_sym):
            out.append(Event(when, "include", add_sym, add_co, source, note))
        if not blank(del_sym):
            out.append(Event(when, "exclude", del_sym, del_co, source, note))
    return out


def parse_500alpha(path: Path) -> list[tuple[int, str, str, str]]:
    rows = list(csv.reader(path.read_text(errors="ignore").splitlines()))
    out = []
    for i, r in enumerate(rows[3:], start=4):
        if len(r) > 3 and re.fullmatch(r"[A-Z][A-Z.]*", r[1].strip()):
            out.append((i, r[1].strip(), r[2].strip(), r[3].strip()))
    return out


def parse_spdr(path: Path) -> list[tuple[int, str]]:
    """Holdings table only (first COMMON STOCKS header to Total Investments).
    Rows end in shares and value; long names wrap onto the next line."""
    lines = path.read_text(errors="ignore").splitlines()
    start = next(i for i, l in enumerate(lines) if "COMMON STOCKS" in l)
    end = next(i for i, l in enumerate(lines) if l.strip().startswith("Total Investments"))
    num = r"\d{1,3}(?:,\d{3})*"
    row = re.compile(rf"^(?P<name>\S.*?)[ .]*\s+{num}\s+\$?\s*{num}\s*$")
    out, pending = [], ""
    for i in range(start, end):
        s = lines[i].rstrip()
        if not s or s.lstrip().startswith(("<", "COMMON STOCKS", "SCHEDULE OF", "SPDR TRUST")) \
                or re.fullmatch(r"\s*[A-Z]+ \d{1,2}, \d{4}", s):
            pending = ""
            continue
        m = row.match(s.strip())
        if m:
            name = (pending + " " + m.group("name")).strip(" .*")
            out.append((i + 1, re.sub(r"\s+", " ", name)))
            pending = ""
        else:
            pending = (pending + " " + s.strip()).strip()
    return out


ABBREV = {"int": "international", "intl": "international", "mfg": "manufacturing",
          "minn": "minnesota", "cos": "companies", "hldg": "holding", "hldgs": "holdings",
          "mtg": "mortgage", "svc": "services", "gp": "group", "providant": "provident"}
NOISE = {"inc", "corp", "corporation", "co", "company", "companies", "ltd", "the", "plc", "new",
         "class", "a", "b", "cl", "com", "incorporated", "limited", "group", "holdings", "holding",
         "and", "l", "de", "nemours", "s"}


def norm_name(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower().replace("&", " and ").replace("'", ""))
    words = [ABBREV.get(w, w) for w in s.split()]
    return " ".join(sorted(w for w in words if w not in NOISE))


def match_level(a: str, b: str) -> int:
    """0 = same words, 1 = one name's words inside the other's, 2 = close spelling, 9 = no match."""
    if a == b:
        return 0
    wa, wb = set(a.split()), set(b.split())
    if wa and wb and (wa <= wb or wb <= wa):
        return 1
    return 2 if difflib.SequenceMatcher(None, a, b).ratio() >= 0.8 else 9


def apply(members: set[str], changes: list[tuple[str, str]], forward: bool) -> list[str]:
    """Apply one date's changes; return contradictions instead of hiding them."""
    bad = []
    for action, sym in (changes if forward else reversed(changes)):
        add = (action == "include") == forward
        if add:
            if sym in members:
                bad.append(f"{action}:{sym} already a member")
            members.add(sym)
        else:
            if sym not in members:
                bad.append(f"{action}:{sym} not a member")
            members.discard(sym)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="parse, roll and report; write nothing")
    ap.add_argument("--dsn", default=os.environ.get("USMARKET_DSN") or DEFAULT_DSN)
    args = ap.parse_args()

    events: list[Event] = []
    for src, *_ in SOURCES:
        if src in YEAR_OF:
            got = parse_change_list(src, REPO / dict((s[0], s[3]) for s in SOURCES)[src])
            log(f"{src}: {len(got)} add/delete rows")
            events += got
    alpha = parse_500alpha(REPO / f"{OLD}/500alpha.csv")
    spdr = parse_spdr(REPO / "sp500_history/sp500probe/spy2001.txt")
    log(f"500alpha.csv: {len(alpha)} members; SPDR 30 Sep 2001: {len(spdr)} holdings")

    # One step per effective date; renames ride in the same step.
    steps: dict[date, list[tuple[str, str]]] = defaultdict(list)
    for e in sorted(events, key=lambda e: (e.after_close, e.action != "exclude")):
        steps[e.effective].append((e.action, e.symbol))
    for ac, old, new, *_ in RENAMES:
        eff = next_trading_day(ac)
        steps[eff] += [("exclude", old), ("include", new)]
    dates = sorted(steps)

    # 1. Where does 500alpha.csv sit? Try every cut; keep the one with fewest contradictions.
    anchor_set = {sym for _, sym, _, _ in alpha}

    def roll(cut: int):
        snaps, bad = {}, []
        m = set(anchor_set)
        snaps[dates[cut]] = set(m)
        for d in dates[cut + 1:]:
            bad += [(d, "roll_forward", b) for b in apply(m, steps[d], forward=True)]
            snaps[d] = set(m)
        m = set(anchor_set)
        for i in range(cut, 0, -1):
            bad += [(dates[i], "roll_backward", b) for b in apply(m, steps[dates[i]], forward=False)]
            snaps[dates[i - 1]] = set(m)
        start = first_trading_day_on_or_after(date(1999, 1, 1))
        bad += [(dates[0], "roll_backward", b) for b in apply(m, steps[dates[0]], forward=False)]
        snaps[start] = set(m)
        return snaps, bad

    scored = sorted((len(roll(k)[1]), k) for k in range(len(dates)))
    best_bad, cut = scored[0]
    ties = [dates[k] for b, k in scored if b == best_bad]
    anchor = dates[cut]
    log(f"500alpha.csv fits the composition effective {anchor} "
        f"({best_bad} contradictions; tied cuts: {[d.isoformat() for d in ties]})")
    snaps, bad = roll(cut)
    nxt = dates[cut + 1] if cut + 1 < len(dates) else None
    as_of_basis = (f"Inferred: matches S&P's composition from {anchor} to "
                   f"{(nxt - timedelta(days=1)) if nxt else 'end'}; file captured 2002-02 to 2003-01")

    # 2. Checks.
    checks = []
    for d, kind, msg in bad:
        checks.append((kind, d, False, None, None, [], [], msg))
    # A count off 500 is explained only when S&P itself printed a deletion with no
    # same-day addition ("-----") and a later one-sided addition restores 500.
    ordered = sorted(snaps.items())
    for i, (d, m) in enumerate(ordered):
        if len(m) == 500:
            continue
        net = sum(1 if a == "include" else -1 for a, _ in steps.get(d, []))
        refill = next((d2 for d2, m2 in ordered[i + 1:] if len(m2) == 500), None)
        gap = len(m) == 499 and net < 0 and refill is not None
        checks.append(("member_count", d, gap, 500, len(m), [], [],
                       f"S&P printed a deletion with no same-day addition; back to 500 on {refill}"
                       if gap else "Count off 500 that S&P's lists do not explain"))

    # SPDR cross-check at 30 Sep 2001 (a Sunday, so the 28 Sep composition), by name.
    names = {sym: co for _, sym, co, _ in alpha}
    for e in events:
        names.setdefault(e.symbol, e.company)
    spdr_day = date(2001, 9, 28)
    roster = snaps[max(d for d in snaps if d <= spdr_day)]
    spdr_norm = {norm_name(n): n for _, n in spdr}
    # One-to-one: pair every exact match first, then word-subset, then close spelling.
    todo = {sym: norm_name(names.get(sym, sym)) for sym in roster}
    used: set[str] = set()
    for level in (0, 1, 2):
        for sym, n in sorted(todo.items()):
            hit = next((k for k in spdr_norm if k not in used and match_level(n, k) == level), None)
            if hit:
                used.add(hit)
                del todo[sym]
    unmatched = [f"{sym} ({names.get(sym, '?')})" for sym in sorted(todo)]
    spdr_only = sorted(v for k, v in spdr_norm.items() if k not in used)
    checks.append(("spdr_name_crosscheck", spdr_day, not unmatched, len(roster), len(spdr), unmatched, spdr_only,
                   f"Fund list, names only: {len(roster) - len(unmatched)} of {len(roster)} members "
                   f"found by name among {len(spdr)} SPDR holdings. Informational, not a checkpoint"))

    first, last_change = min(snaps), dates[-1]
    covered_through = date(2002, 11, 29)   # last trading day before the 2002 list's 1 Dec capture
    log(f"snapshots: {len(snaps)} from {first} to {last_change}; coverage {first}..{covered_through}")
    failed = [c for c in checks if not c[2]]
    log(f"checks: {len(checks)} run, {len(failed)} not reconciled")
    for c in failed[:40]:
        log(f"   {c[0]:<22} {c[1]}  {c[7]}" + (f"  count={c[4]}" if c[0] == 'member_count' else "")
            + (f"  unmatched={len(c[5])}" if c[5] else ""))

    if args.dry_run:
        log("dry run: nothing written")
        return 0

    import psycopg2  # noqa: PLC0415
    from psycopg2.extras import execute_values  # noqa: PLC0415

    with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute((HERE / "schema.sql").read_text())
        for t in ("index_membership", "index_membership_coverage", "index_membership_reconciliation",
                  "index_change_event", "index_symbol_change", "index_constituent_list"):
            cur.execute(f"delete from usmarket.{t} where index_type = %s", (INDEX,))
        execute_values(cur, """insert into usmarket.index_source_file
            (source, publisher, kind, path, url, captured_on, note) values %s
            on conflict (source) do update set publisher = excluded.publisher, kind = excluded.kind,
              path = excluded.path, url = excluded.url, captured_on = excluded.captured_on,
              note = excluded.note""", SOURCES)
        execute_values(cur, """insert into usmarket.index_change_event
            (index_type, after_close_date, effective_date, action, symbol, company, source, note) values %s""",
            [(INDEX, e.after_close, e.effective, e.action, e.symbol, e.company, e.source, e.note)
             for e in events])
        if RENAMES:
            execute_values(cur, """insert into usmarket.index_symbol_change
                (index_type, effective_date, old_symbol, new_symbol, company, source, note) values %s""",
                [(INDEX, next_trading_day(ac), o, n, co, s, nt) for ac, o, n, co, s, nt in RENAMES])
        execute_values(cur, """insert into usmarket.index_constituent_list
            (source, line_no, index_type, as_of_date, as_of_basis, symbol, company, industry) values %s""",
            [("sp_500alpha", ln, INDEX, anchor, as_of_basis, sym, co, ind) for ln, sym, co, ind in alpha]
            + [("spdr_n30d_20010930", ln, INDEX, date(2001, 9, 30), "Stated: annual report date",
                None, n, None) for ln, n in spdr])
        rows = []
        for d, m in snaps.items():
            src = "sp_500alpha" if d == anchor else "sp_changes:roll_from_sp_500alpha"
            rows += [(INDEX, d, s, src, d == anchor) for s in sorted(m)]
        execute_values(cur, """insert into usmarket.index_membership
            (index_type, effective_date, symbol, source, is_verified) values %s""", rows, page_size=5000)
        cur.execute("""insert into usmarket.index_membership_coverage values (%s, %s, %s, %s)""",
                    (INDEX, first, covered_through,
                     "S&P change lists 1999 to 18 Nov 2002, rolled from 500alpha.csv; "
                     "the 2002 list was captured 1 Dec 2002"))
        execute_values(cur, """insert into usmarket.index_membership_reconciliation
            (index_type, check_name, check_date, reconciled, expected, actual, missing, extra, note) values %s
            on conflict (index_type, check_name, check_date) do update
              set note = usmarket.index_membership_reconciliation.note || ' | ' || excluded.note,
                  reconciled = false""",
            [(INDEX, *c) for c in checks])
    log(f"wrote {len(rows)} membership rows, {len(events)} change rows, {len(checks)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
