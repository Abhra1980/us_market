#!/usr/bin/env python3
"""Point-in-time S&P 500 membership, Dec 2002 to Dec 2009, into schema usmarket.

This closes the gap between build_sp500_membership.py (1999 to Nov 2002) and
build_sp500_modern.py (Jan 2010 onward). Run it after both: it starts from the first's
last list and must arrive at the second's first list.

THE SOURCES
-----------
* S&P's own change notices for 2003-2009 (``fetch_sp_press_2003_2009.py`` ->
  data/sp500_changes_2003_2009.csv): Wayback copies of S&P's index pages and S&P's
  releases as wire services carried them, each with the URL it was read from.
* Full holdings lists of S&P 500 index funds from their SEC filings (N-CSR, N-CSRS, N-Q)
  (``fetch_sec_fundlists_2002_2009.py`` -> downloads/sec/fund_holdings_2002_2009.csv).
  Names only: no CUSIPs and no tickers before 2019.
* The SEC's fails-to-deliver files from Mar 2004 (``fetch_sec_holdings.py --ftd-from 2004-03``):
  CUSIP, ticker and the SEC's issuer description, with first and last sighting. They turn
  a fund's company name into a ticker, and date ticker changes S&P did not list.
* The SEC's quarterly lists of 13(f) securities from 2002 Q4 (``fetch_sec_13f_lists.py``):
  issuer names by CUSIP, the only dated SEC names before the fails data starts.

THE METHOD
----------
1. Start: the members effective 29 Nov 2002, as build_sp500_membership.py wrote them.
2. Roll S&P's 2003-2009 changes forward, one snapshot per change date.
3. At every fund month-end, name each fund holding by matching it to the SEC's issuer
   description of a ticker trading at that date, and compare with the roll. Another share
   class of a member, and an old name on the same CUSIP, are not differences. Each other
   difference is labelled: timing around an S&P date, a stock kept after S&P deleted it, a
   stock a deal or spin-off handed the fund, or a member the fund did not hold. A month-end
   is confirmed when some fund's list there matches exactly or differs only by timing; a
   stretch between two confirmed month-ends is written as verified.
4. End: the roll on 4 Jan 2010 must equal the list build_sp500_modern.py starts from.

Changes the fund lists show but no S&P notice survives for are listed below
(NO_NOTICE), each with its evidence and how it was dated. Every check, passed or not,
goes to index_membership_reconciliation.

Usage:
    python3 sp500_history/membership/build_sp500_2003_2009.py --dry-run
    python3 sp500_history/membership/build_sp500_2003_2009.py
"""
from __future__ import annotations

import argparse
import csv
import difflib
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
CHANGES = HERE / "data/sp500_changes_2003_2009.csv"
TICKER_CHANGES = HERE / "data/sp500_ticker_changes_2003_2009.csv"
FUND_SUMMARY = HERE / "data/fund_lists_2002_2009_summary.csv"
FUND_HOLDINGS = SEC / "fund_holdings_2002_2009.csv"
FTD_FILES = (SEC / "ftd_cusip_symbol_2004_2009.csv", SEC / "ftd_cusip_symbol.csv")
LOOKUP_13F = SEC / "cusip_name_symbol_2002_2010.csv"   # fetch_sec_13f_lists.py
PLACEHOLDER = re.compile(r"XXXX|ZZZZ|YYYY")           # the SEC's temporary symbols around a CUSIP change
NAME_FILES = (SEC / "ftd_cusip_names_2004_2009.csv", SEC / "ftd_cusip_names.csv")   # fetch_sec_holdings.py
FIRST = date(2002, 11, 29)      # last day build_sp500_membership.py covers
LAST = date(2010, 1, 4)         # first day build_sp500_modern.py covers
FTD_WINDOW = 60                 # days either side of a date a CUSIP->ticker pair may be used
NAME_WINDOW = 3650              # how far back a ticker's earlier CUSIPs (and so their names) still count
SOURCE_PRESS = "sp_press_2003_2009"
SOURCE_FUNDS = "sec_ncsr_nq_sp500_funds_2002_2009"
SOURCE_FTD = "sec_fails_to_deliver_2004_2009"


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


def key(sym: str) -> str:
    """One spelling per ticker: S&P writes BRK.B and VIA.B, the SEC VIAB."""
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"wi$", "", sym.strip())).upper()


# ---------------------------------------------------------------------------------------
# Names. Fund lists print "Exxon Mobil Corp.", the SEC "EXXON MOBIL CORPORATION" or
# "GEN MOTORS CORP;COM USD1-2/3". Both are reduced to their distinctive words.
ABBREV = {
    "int": "international", "intl": "international", "internat": "international", "mfg": "manufacturing",
    "cos": "companies", "hldg": "holding", "hldgs": "holdings", "hlds": "holdings", "mtg": "mortgage",
    "svc": "services", "svcs": "services", "gp": "group", "grp": "group", "gen": "general",
    "finl": "financial", "fin": "financial", "tech": "technology", "technologies": "technology",
    "tel": "telephone", "teleph": "telephone", "comm": "communications", "communication": "communications",
    "commun": "communications", "pharm": "pharmaceutical", "pharmaceuticals": "pharmaceutical",
    "pharmaceutcl": "pharmaceutical", "ins": "insurance", "natl": "national", "nat": "national",
    "amer": "american", "am": "american", "ind": "industries", "inds": "industries", "industry": "industries",
    "elec": "electric", "pwr": "power", "res": "resources", "resource": "resources", "sys": "systems",
    "system": "systems", "bancorporation": "bancorp", "mgmt": "management", "dev": "development",
    "labs": "laboratories", "lab": "laboratories", "ent": "entertainment", "prods": "products",
    "product": "products", "mach": "machines", "bus": "business", "ctr": "center", "ctrs": "centers",
    "util": "utilities", "trst": "trust", "svgs": "savings", "props": "properties", "ppty": "property",
    "sts": "states", "wm": "william", "dept": "department", "depts": "department", "ln": "loan",
    "fed": "federal", "assn": "association", "stores": "store", "brands": "brand", "us": "u s", "usa": "u s", "st": "st", "saint": "st", "intergrated": "integrated",
}
NOISE = {
    "inc", "corp", "corporation", "co", "company", "companies", "ltd", "the", "plc", "new", "cl", "com",
    "incorporated", "limited", "group", "holdings", "holding", "and", "l", "de", "s", "a", "b", "class",
    "shs", "sh", "stk", "common", "stock", "ord", "par", "usd", "registered", "reg", "nv", "n", "v", "sa",
    "ag", "se", "lp", "llc", "trust", "the", "of", "tr", "ser", "series", "spl", "special", "non", "voting",
    "nonvoting", "vtg", "nvs", "reit", "adr", "ads", "sponsored", "fund", "shares", "share", "unit", "units", "del", "md",
    "ny", "nj", "pa", "va", "oh", "wis", "ind", "inds", "industries", "co", "cp",
}


ALIASES = {"freddie mac": "federal home loan mortgage", "fannie mae": "federal national mortgage association",
           "metropolitan life insurance": "metlife", "nasdaq stock market": "nasdaq omx",
           r"\bibm\b": "international business machines"}
NOT_COMMON = re.compile(r"\b(PFD|PREF|PREFERRED|WARR|WARRANTS?|WTS?|RIGHTS?|RTS?|DEB|DBCV|NOTES?|UNITS?|CONV|"
                        r"DEPOSITARY|TRUST PFD)\b|%")


def norm_words(s: str) -> list[str]:
    s = s.split(";")[0].replace("\u2019", "'")              # SEC: "NAME;COM USD1" -> "NAME"
    for nick, full in ALIASES.items():
        s = re.sub(nick, full, s, flags=re.I)
    s = s.lower().replace("'", "").replace(".", " ").replace("at&t", "att")
    s = re.sub(r"\b([a-z])\s*&\s*([a-z])\b", r"\1\2", s)       # H&R, AT&T -> hr, att
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("&", " and "))
    words = s.split()
    joined = []                                                 # "W W Grainger", "V F" -> ww, vf
    for w in words:
        if len(w) == 1 and joined and re.fullmatch(r"[a-z]+", joined[-1]) and joined[-1].isalpha() \
                and len(joined[-1]) <= 3 and joined[-1] not in ABBREV and joined[-1] not in NOISE - {"a", "b", "s", "l", "n", "v"}:
            joined[-1] += w
        else:
            joined.append(w)
    out = []
    for w in joined:
        out += ABBREV.get(w, w).split()
    kept = [w for w in out if w not in NOISE and not re.fullmatch(r"\d+(\d|/)*", w)]
    return kept or [w for w in out if w not in ("the", "inc", "co", "corp", "company")]   # "The Limited, Inc."


def share_class(s: str) -> tuple[str, bool]:
    """(class letter or '', special?) from a fund line or an SEC description: "Class C (non-vtg.)"
    -> ('C', False), "COMCAST CORP CL A SPL" -> ('A', True)."""
    t = s.upper()
    m = re.search(r"\b(?:CLASS|CL)\s*\.?\s*([A-C])\b", t) or re.search(r"\bSER(?:IES)?\s+([A-C])\b", t)
    return (m.group(1) if m else "", bool(re.search(r"\bSPECIAL\b|\bSPL\b|\bSPCL\b", t)))


def similarity(a: list[str], b: list[str]) -> float:
    """How alike two reduced names are, in any word order: 1.0 same words; 0.85-1.0 when every
    word of the shorter name opens a word of the longer one (the SEC truncates and reorders
    names: "GRAINGER W W INC", "LILLY ELI & CO"); else their spelling ratio."""
    if not a or not b:
        return 0.0
    if a == b or sorted(a) == sorted(b) or "".join(a) == "".join(b):
        return 1.0
    sa, sb = set(a), set(b)

    def opens(w: str, ys: set[str]) -> bool:
        return w in ys or any(min(len(w), len(y)) >= 3 and (y.startswith(w) or w.startswith(y)) for y in ys)
    short, long_ = (a, sb) if len(sa) <= len(sb) else (b, sa)
    if all(opens(w, long_) for w in short):
        if len(set(short)) == 1 and len(long_) > 1:        # one word inside a longer name: only as its start
            lead = (b if short is a else a)[0]
            return 0.86 if short[0] == lead or (len(short[0]) >= 3 and (lead.startswith(short[0])
                                                                       or short[0].startswith(lead))) else 0.8
        return 0.85 + 0.15 * len(sa & sb) / len(sa | sb)
    ja, jb = "".join(sorted(a)), "".join(sorted(b))
    return difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio() * 0.8 + \
        0.2 * difflib.SequenceMatcher(None, ja, jb).ratio()


# ---------------------------------------------------------------------------------------
# Changes missing from S&P's surviving pages, found through the reconciliation below. Each:
# (effective date, action, ticker, company, evidence, URL of the text it was read from).
ROPER = ("S&P's wording as Briefing.com carried it on 22 Dec 2009: \"S&P MidCap 400 constituent Roper "
         "Industries (ROP) will replace ENSCO International (ESV) in the S&P 500 ... after the close of "
         "trading\" (WSJ the same day: after the close on Dec. 22). Every fund list of 31 Dec 2009 holds ROP, "
         "none ESV")
NO_NOTICE: list[tuple[str, str, str, str, str, str]] = [
    ("2009-12-23", "exclude", "ESV", "ENSCO International", ROPER,
     "https://insurancenewsnet.com/oarticle/Briefingcom-Hourly-In-Play-R-1600-ET-a-149162"),
    ("2009-12-23", "include", "ROP", "Roper Industries", ROPER,
     "https://insurancenewsnet.com/oarticle/Briefingcom-Hourly-In-Play-R-1600-ET-a-149162"),
]
# Ticker changes of members no S&P notice survives for (old, new, date, evidence).
NO_NOTICE_RENAMES: list[tuple[str, str, str, str]] = [
]

SOURCES = [
    (SOURCE_PRESS, "S&P", "change_list", "sp500_history/membership/data/sp500_changes_2003_2009.csv",
     "https://web.archive.org/", None,
     "S&P's 2003-2009 S&P 500 change notices: Wayback copies of S&P's index pages and S&P's releases "
     "as wire services carried them (see release_url per row)"),
    (SOURCE_FUNDS, "Vanguard 500, Fidelity Spartan 500, Schwab S&P 500, SPDR, iShares S&P 500 (SEC N-CSR/N-Q)",
     "fund_holdings", "sp500_history/downloads/sec/fund_holdings_2002_2009.csv",
     "https://www.sec.gov/cgi-bin/browse-edgar", None,
     "Full holdings schedules by name; together about every month-end from mid-2004. Checkpoints only"),
    (SOURCE_FTD, "SEC", "constituent_list", "sp500_history/downloads/sec/ftd_cusip_symbol_2004_2009.csv",
     "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data", None,
     "CUSIP <-> ticker <-> issuer description, Mar 2004 to Jun 2009; names fund holdings and dates "
     "deletions of companies that stopped trading"),
]


@dataclass(frozen=True)
class Change:
    effective: date
    action: str            # include | exclude
    symbol: str
    company: str
    announced: date | None
    url: str
    note: str
    source: str


def load_changes() -> tuple[list[Change], list[dict]]:
    """S&P's dated rows (its own pages, or its release as a wire carried it)."""
    ok, other, seen = [], [], set()
    if not CHANGES.exists():
        return ok, other
    for r in csv.DictReader(CHANGES.open()):
        if r["status"] not in ("ok", "wire_copy") or not r["symbol"] or not r["effective_date"]:
            other.append(r)
            continue
        once = (r["effective_date"], r["action"], key(r["symbol"]))
        if once in seen:
            continue
        seen.add(once)
        ok.append(Change(date.fromisoformat(r["effective_date"]), r["action"], r["symbol"].strip(),
                         r["company"], date.fromisoformat(r["announced_date"]) if r["announced_date"] else None,
                         r["release_url"], r["note"], SOURCE_PRESS))
    return ok, other


def load_ftd() -> dict[str, list[tuple[str, date, date, str]]]:
    """cusip -> [(ticker, first, last, SEC description)], both fails files merged."""
    out: dict[str, dict] = defaultdict(dict)
    for f in FTD_FILES:
        for r in csv.DictReader(f.open()):
            if r["placeholder"] == "Y" or not r["symbol"].strip():
                continue
            k = (key(r["symbol"]), r["description"].replace("\x00", ""))
            a, b = date.fromisoformat(r["first_seen"]), date.fromisoformat(r["last_seen"])
            old = out[r["cusip"]].get(k)
            out[r["cusip"]][k] = (min(a, old[0]), max(b, old[1])) if old else (a, b)
    return {c: [(s, a, b, d) for (s, d), (a, b) in v.items()] for c, v in out.items()}


NOT_A_STOCK = re.compile(r"\b(warrants?|rights?|contingent value|escrow|futures?|repurchase|money market|"
                         r"cash|collateral|miscellaneous)\b", re.I)


def load_ftd_names() -> dict[str, list[tuple[str, date, date, str]]]:
    """cusip -> [(ticker, first, last, SEC description)] with each description's own dates (the
    pairs files keep only the latest description: CVS HEALTH for a 2010 fund line "CVS Caremark")."""
    if not all(f.exists() for f in NAME_FILES):
        return load_ftd()
    out: dict[str, list] = defaultdict(list)
    for f in NAME_FILES:
        for r in csv.DictReader(f.open()):
            if r["symbol"].strip() and not PLACEHOLDER.search(r["symbol"]):
                out[r["cusip"]].append((key(r["symbol"]), date.fromisoformat(r["first_seen"]),
                                        date.fromisoformat(r["last_seen"]), r["description"].replace("\x00", "")))
    return out


def load_13f(ftd: dict) -> int:
    """Add the SEC 13(f) lists' issuer names (2002 Q4 onward) to the fails data, under the ticker
    the same CUSIP first traded as. Before Mar 2004 these are the only SEC names with a date."""
    added = 0
    for r in csv.DictReader(LOOKUP_13F.open()):
        if not r["issuer_names"] or not r["symbols"] or not re.search(r"\b(COM|CL|SHS|ORD|SH)\b", r["issue_descriptions"]):
            continue
        syms = sorted((a, s) for s, a, _ in re.findall(r"([^|\[]+?) \[(\S+)\.\.(\S+)\]", r["symbols"])
                      if "placeholder" not in s)
        if not syms:
            continue
        sym = key(syms[0][1])
        for name, q1, q2 in re.findall(r"([^|\[]+?) \[(\d{4}q\d)\.\.(\d{4}q\d)\]", r["issuer_names"]):
            a = date(int(q1[:4]), 3 * int(q1[-1]) - 2, 1)
            b = date(int(q2[:4]) + (q2[-1] == "4"), (3 * int(q2[-1])) % 12 + 1, 1) - timedelta(days=1)
            ftd.setdefault(r["cusip"], []).append((sym, a, b, name.strip().removesuffix(" ocr").strip()))
            added += 1
    return added


# Names a filing misprints, read as the holding they are. Each with its evidence.
FUND_NAME_FIXES = {
    ("FUSEX", "Pricoa Global Funding I"): (
        "Prudential Financial, Inc.",
        "Fidelity's Feb and May 2016 schedules print Prudential's funding subsidiary in Prudential's "
        "alphabetical place among the insurers; Feb 2016: 2,279,841 shares worth $150.7M ($66.09 a share, "
        "Prudential's price that month)"),
}
NON_STOCK_OTHER = re.compile(r"cash|fund|money|treasury|bill|note|reserve|trust|portfolio|deposit|liquid|govern|"
                             r"agency|paper|coupon|face|expires|\d", re.I)
COMPANY = re.compile(r"\b(inc|ltd|corp|co|plc|company)\.?$", re.I)


def load_fund_lists(summary: Path = FUND_SUMMARY, holdings: Path = FUND_HOLDINGS
                    ) -> dict[tuple[str, date], list[tuple[int, str, str]]]:
    """(fund, period end) -> [(line_no, name, section)] for stock lines of complete schedules."""
    usable = set()
    for r in csv.DictReader(summary.open()):
        if r["complete"] == "true":            # 480-520 lines adding up to the filing's own stock total
            usable.add((r["fund"], r["period_end"]))
    lists: dict = defaultdict(list)
    for r in csv.DictReader(holdings.open()):
        name = re.sub(r"^(table of contents\s*)?[\s^*\u2020\u2021#@+()-]*", "", r["name"], flags=re.I).strip()
        if (r["fund"], r["period_end"]) not in usable or NOT_A_STOCK.search(name):
            continue
        # The fetcher files money funds, cash and coupons under "other"; one company landed there
        # too (Schwab's "Invesco Ltd.", 2008-09). Keep an "other" line only if it reads as a company.
        if r["section"].startswith("other") and (NON_STOCK_OTHER.search(name) or not COMPANY.search(name)):
            continue
        name = FUND_NAME_FIXES.get((r["fund"], name), (name,))[0]
        lst = lists[(r["fund"], date.fromisoformat(r["period_end"]))]
        # Fidelity prints "News Corp.: Class A" then a line "Class B": give it the company.
        if re.match(r"(?i)class\s+[a-c]\b", name) and lst and ":" in lst[-1][1]:
            name = lst[-1][1].split(":")[0] + ": " + name
        lst.append((int(r["line_no"]), name, r["section"]))
    return lists


def db_rows(dsn: str, sql: str, params=()) -> list[tuple]:
    import psycopg2  # noqa: PLC0415
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


class Namer:
    """Names a fund holding: which ticker's issuer it is, at a date."""

    def __init__(self, ftd: dict, known_names: dict[str, set[str]], dated_names=(), renames=()):
        self.rows = [(c, s, a, b, d, norm_words(d)) for c, pairs in ftd.items() for s, a, b, d in pairs]
        self.by_word = defaultdict(list)
        self.by_sym = defaultdict(list)
        self.by_cusip = defaultdict(list)
        for i, r in enumerate(self.rows):
            self.by_cusip[r[0]].append(i)
            for w in set(r[5]):
                if len(w) >= 2:
                    self.by_word[w].append(i)
            self.by_sym[r[1]].append(i)
        self.known = {k: [norm_words(n) for n in v] for k, v in known_names.items()}   # ticker -> S&P's names
        self.came_from = defaultdict(list)          # new ticker -> [(rename date, old ticker)]
        for d, o, n in renames:
            self.came_from[n].append((d, o))
        self.dated = defaultdict(list)                                                  # ticker -> (name, from, to)
        for sym, n, a, b in dated_names:
            self.dated[sym].append((norm_words(n), a, b))

    def names_of(self, sym: str, d: date, depth: int = 0) -> list[tuple[list[str], str]]:
        """Reduced names a ticker went by near d: the SEC's descriptions, then S&P's names."""
        # A member's names over the year around d: funds print a company's old name for months
        # ("Sprint Corp. (FON Group)" in 2006). Safe, as only the roll's members are matched this way.
        # The CUSIPs are the ones the ticker traded under up to d (tickers are reused: S was Sears,
        # then Sprint, so never a later CUSIP); the names are every name those CUSIPs carried up to
        # d, however old (Fidelity still printed "MGM Mirage" in 2018, eight years after the rename).
        lo, hi = d - timedelta(days=NAME_WINDOW), d + timedelta(days=FTD_WINDOW)
        cus = {self.rows[i][0] for i in self.by_sym.get(sym, []) if self.rows[i][2] <= hi and self.rows[i][3] >= lo}
        out = [(r[5], r[4]) for c in cus for j in self.by_cusip[c] for r in [self.rows[j]] if r[2] <= hi]
        if not out:      # before Mar 2004, or never failed: any sighting, then S&P's own names
            out = [(self.rows[i][5], self.rows[i][4]) for i in self.by_sym.get(sym, [])]
        # A renamed member also answers to the names of the ticker it came from (Fidelity printed
        # "McGraw Hill Financial" for S&P Global, SPGI, and "Quintiles Transnational" for IQVIA).
        older = [x for rd, o in self.came_from.get(sym, []) if rd <= d + timedelta(days=FTD_WINDOW) and depth < 3
                 for x in self.names_of(o, rd - timedelta(days=1), depth + 1)]
        return out + older + [(w, "S&P") for w in self.known.get(sym, [])] + \
            [(w, "S&P, before a ticker change") for w, a, b in self.dated.get(sym, []) if a <= d <= b]

    def cusips_of(self, sym: str, d: date) -> set[str]:
        """The CUSIPs a ticker traded under near d (any date if none near)."""
        rows = [self.rows[i] for i in self.by_sym.get(sym, [])]
        near = {r[0] for r in rows if r[2] - timedelta(days=FTD_WINDOW) <= d <= r[3] + timedelta(days=FTD_WINDOW)}
        return near or {r[0] for r in rows}

    def candidates(self, name: str, d: date) -> list[tuple[float, str, str]]:
        """Tickers trading near d whose SEC description matches the name, best first."""
        w = norm_words(name)
        if not w:
            return []
        idx = {i for v in w if len(v) >= 2 for i in self.by_word.get(v, [])}
        if not idx:                         # "ChevronTexaco" vs "CHEVRON TEXACO": by opening letters
            j = "".join(w)
            idx = {i for i, r in enumerate(self.rows) if r[5] and "".join(r[5])[:6] == j[:6]}
        out = {}
        for i in idx:
            c, s, a, b, desc, rw = self.rows[i]
            if not (a - timedelta(days=FTD_WINDOW) <= d <= b + timedelta(days=FTD_WINDOW)) or NOT_COMMON.search(desc):
                continue
            sc = similarity(w, rw) + class_bonus(name, desc)
            if sc > out.get(s, (0,))[0]:
                out[s] = (sc, desc)
        return sorted(((sc, s, desc) for s, (sc, desc) in out.items()), reverse=True)


def class_bonus(a: str, b: str) -> float:
    (la, sa), (lb, sb) = share_class(a), share_class(b)
    bonus = (0.05 if la == lb else -0.1) if la and lb else 0.0
    if sa or sb:                     # Comcast's special class A line against its class A line
        bonus += 0.03 if sa == sb else -0.05
    return bonus


MATCH = 0.85


def check_list(namer: Namer, lines: list, roll: frozenset, d: date):
    """Match one fund list to the roll effective on d. Returns (named, missing, extra, unnamed):
    named = line -> ticker; missing = tickers the fund holds that the roll lacks; extra = roll
    members no fund line matched; unnamed = fund lines matching no ticker at all."""
    names = {sym: namer.names_of(sym, d) for sym in roll}
    near = defaultdict(set)                 # opening letters of each word -> roll tickers
    for sym, ns in names.items():
        for rw, _ in ns:
            for x in rw + ["".join(rw)]:
                near[x[:4]].add(sym)
    scores = []
    for ln, name, _ in lines:
        w = norm_words(name)
        for sym in {s for x in w + ["".join(w)] for s in near.get(x[:4], ())}:
            best = max((similarity(w, rw) + class_bonus(name, desc) for rw, desc in names[sym]), default=0.0)
            if best >= MATCH:
                scores.append((best, ln, sym))
    named, used = {}, set()
    for sc, ln, sym in sorted(scores, reverse=True):
        if ln not in named and sym not in used:
            named[ln] = sym
            used.add(sym)
    missing, unnamed, excused = {}, [], []
    for ln, name, _ in lines:
        if ln in named:
            continue
        w = norm_words(name)
        sib = next((sym for sym in sorted(used) for rw, _ in names[sym] if similarity(w, rw) >= MATCH), None)
        if sib:                     # "Wm. Wrigley Jr. Co." beside "... Class B": another class of a member
            excused.append(f"{name} (another line of member {sib})")
            continue
        cands = [c for c in namer.candidates(name, d) if c[0] >= MATCH and c[1] not in used]
        if cands:
            missing[ln] = cands[0][1]
            named[ln] = cands[0][1]
        else:
            unnamed.append((ln, name))
    extra = sorted(roll - used)
    # A misprinted name ("ennar Corp." for Lennar, Schwab Jul 2009): an unnamed line whose spelling is
    # very close to the name of a member no line matched.
    for u in list(unnamed):
        j = "".join(norm_words(u[1]))
        hit = max(((difflib.SequenceMatcher(None, j, "".join(rw)).ratio(), x) for x in extra
                   for rw, _ in names[x] if rw), default=(0, None))
        if hit[0] >= 0.9:
            named[u[0]] = hit[1]
            extra.remove(hit[1])
            unnamed.remove(u)
            excused.append(f"{u[1]!r} read as {hit[1]} (misprinted name)")
    # A fund-only ticker and a roll-only ticker on the same CUSIP are one security under two
    # labels (a fund printing the old name after a rename, or the SEC's ticker lagging S&P's).
    # A fund-only ticker whose issuer (CUSIP's first six characters) is a member's is another
    # share class of that member, which funds hold and the index does not carry.
    for ln, t in list(missing.items()):
        cs = namer.cusips_of(t, d)
        twin = next((x for x in extra if cs & namer.cusips_of(x, d)), None)
        if twin:
            named[ln] = twin
            extra.remove(twin)
            del missing[ln]
            excused.append(f"{t}={twin} (same CUSIP)")
            continue
        issuers = {c[:6] for c in cs}
        sib = next((x for x in sorted(used) if issuers & {c[:6] for c in namer.cusips_of(x, d)}), None)
        if sib:
            del missing[ln]
            excused.append(f"{t} (other share class of member {sib})")
    return named, missing, extra, unnamed, excused


TEMP_SUFFIXES = ("D", "E", "Q", "X", "XX")


def ftd_renames(ftd: dict) -> list[tuple[date, str, str, str]]:
    """One CUSIP whose ticker changed, dated by the new ticker's first sighting (SEC fails data).
    Applied only to members, like every rename."""
    out, plain = [], re.compile(r"^[A-Z]{1,5}$")
    for c, pairs in ftd.items():
        seq = sorted((a, b, s) for s, a, b, _ in pairs if plain.match(s))
        for (f1, l1, old), (f2, l2, new) in zip(seq, seq[1:]):
            if old == new or not (FIRST < f2 <= LAST) or not (f1 < f2 and l2 >= l1):
                continue
            if any(new == old + x or old == new + x for x in TEMP_SUFFIXES):
                continue                     # temporary suffixes: CIEND (reverse split), WLPXX, ...E (late filer)
            out.append((on_or_after(f2), old, new,
                        f"CUSIP {c} traded as {old} until {l1} and as {new} from {f2} (SEC fails data)"))
    return out


def classify(results: list, steps: dict, applied_renames: list) -> tuple[set, list, set]:
    """Label every difference between the fund lists and the roll (appended to each result's
    notes); return the confirmed month-ends and the cross-fund suspects. Shared with
    build_sp500_modern.py for its 2010-2019 name-only lists."""
    # Why each difference is there. Funds trade around S&P's dates and keep what a deal or a
    # spin-off hands them; anything else is a candidate for a change the roll is missing.
    when = defaultdict(list)                 # ticker -> [(effective, action)]
    for d in steps:
        for op, k, new in steps[d]:
            if op in ("include", "exclude"):
                when[k].append((d, op))

    def why(t: str, side: str, p: date) -> str:
        want = "exclude" if side == "fund" else "include"
        if t not in when and t[-1:] in ("D", "E", "Q") and t[:-1] in when:
            t = t[:-1]                          # PMTCD, a temporary ticker of PMTC
        # A fund trades a few days before or after S&P's date (it buys an addition early, keeps
        # a deletion until a deal closes), so any S&P change of the ticker within 10 days explains it.
        near = [(d, op) for d, op in when.get(t, []) if -10 <= (d - p).days <= 10]
        if near:
            return f"timing: S&P {'deleted' if near[0][1] == 'exclude' else 'added'} {t} effective {near[0][0]}"
        ren = [d for d, o, n in applied_renames if t in (o, n) and -10 <= (d - p).days <= 10]
        if ren:
            return f"timing: {t} changed ticker effective {ren[0]}"
        if side == "fund":
            gone = [d for d, op in when.get(t, []) if op == "exclude" and d <= p]
            if gone:
                return f"fund still held {t} after S&P deleted it effective {max(gone)}"
            return f"not an index member: {t} came to the fund from a deal or spin-off, or the fund chose it"
        return f"fund did not hold member {t}"
    persist = Counter()
    for r in results:
        for t in r[4].values():
            r[7].append("fund-only " + why(t, "fund", r[0]))
            if why(t, "fund", r[0]).startswith("not an index"):
                persist[("fund", t)] += 1
        for t in r[5]:
            w = why(t, "roll", r[0])
            r[7].append("roll-only " + w)
            if not w.startswith("timing"):
                persist[("roll", t)] += 1
    log(f"differences not explained by S&P's dates, by ticker and month-ends seen: "
        f"{sorted(persist.items(), key=lambda kv: -kv[1])}")

    # Cross-fund: a member one fund did not hold is a fund lag if another fund held it within 45
    # days; if no fund held it, S&P may have deleted it without a surviving notice. A non-member
    # every fund held within 45 days may be a missing S&P addition. Both lists should be empty.
    held = [(r[0], r[1], set(r[3].values())) for r in results]
    suspects = []
    for r in results:
        near = [(p2, f2, h) for p2, f2, h in held if abs((p2 - r[0]).days) <= 45 and (p2, f2) != (r[0], r[1])]
        for t in r[5]:
            if why(t, "roll", r[0]).startswith("timing"):
                continue
            who = next(((p2, f2) for p2, f2, h in near if t in h), None)
            if who:
                r[7].append(f"roll-only {t}: {who[1]} held it at {who[0]} (a lag at {r[1]})")
            else:
                suspects.append((r[0], f"member {t} held by no fund list within 45 days of {r[0]}"))
        for t in r[4].values():
            if why(t, "fund", r[0]).startswith("not an index") and near and all(t in h for _, _, h in near):
                suspects.append((r[0], f"non-member {t} held by every fund list within 45 days of {r[0]}"))
    log(f"cross-fund suspects (a change the roll may be missing): {suspects}")

    # A month-end is confirmed when at least one fund's list there equals the roll exactly, or
    # when every difference in some fund's list is timing around one of S&P's own dates.
    by_p = defaultdict(list)
    for r in results:
        by_p[r[0]].append(r)

    def clean(r) -> bool:
        if r[6]:
            return False
        diffs = [x for x in r[7] if x.startswith(("fund-only", "roll-only"))]
        return all(": timing:" in x.replace("only timing", "only: timing") or "timing:" in x for x in diffs)
    confirmed = {p for p, rs in by_p.items() if any(clean(r) for r in rs)}

    def open_items(r) -> list[str]:
        """Differences with no stored cause: a member no other fund held either, a fund line
        that names no ticker, a non-member every fund held."""
        lagged = {x.split(":")[0].split()[-1] for x in r[7] if "(a lag at" in x}
        out = [f"member {t} not held" for t in r[5]
               if not why(t, "roll", r[0]).startswith("timing") and t not in lagged]
        out += [f"unnamed line {u[1]!r}" for u in r[6]]
        out += [m for d, m in suspects if d == r[0] and any(t in m for t in r[4].values())]
        return out
    explained = {p for p, rs in by_p.items() if p not in confirmed and any(not open_items(r) for r in rs)}
    for r in results:
        r[7].append("open: " + ("; ".join(open_items(r)) or "none"))
    for p in sorted(set(by_p) - confirmed):
        best = min(by_p[p], key=lambda r: len(r[4]) + len(r[5]) + len(r[6]))
        log(f"   unconfirmed {p} {best[1]}: " + "; ".join(x for x in best[7] if x.startswith(("fund-only", "roll-only")))
            + (f"; unnamed {[u[1] for u in best[6]]}" if best[6] else ""))
    unexplained = sorted(set(by_p) - confirmed - explained)
    log(f"month-ends: {len(confirmed)} confirmed (a fund list matches exactly or only by S&P-date timing), "
        f"{len(explained)} explained (every difference in some fund's list has a stored cause), "
        f"{len(unexplained)} unexplained {[str(p) for p in unexplained]}, of {len(by_p)}")
    return confirmed, suspects, explained


def month_end_status(index: str, results: list, confirmed: set, explained: set) -> list[tuple]:
    """One reconciliation row per fund month-end: confirmed, explained or unexplained."""
    rows = []
    for p in sorted({r[0] for r in results}):
        st = "confirmed" if p in confirmed else "explained" if p in explained else "unexplained"
        funds = "+".join(r[1] for r in results if r[0] == p)
        rows.append((index, "month_end_status", p, st != "unexplained", None, None, [], [],
                     f"{st}: " + {"confirmed": "a fund list matches the roll exactly or differs only by timing "
                                                "around S&P's own dates",
                                  "explained": "every difference in at least one fund's list has a stored cause "
                                               "(timing, a stock kept after S&P deleted it, deal or spin-off shares, "
                                               "another fund holding the member)",
                                  "unexplained": "a difference with no stored cause"}[st] + f" ({funds})"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="build and check; write nothing")
    ap.add_argument("--dsn", default=os.environ.get("USMARKET_DSN") or DEFAULT_DSN)
    ap.add_argument("--show", type=int, default=40, help="discrepancies to print per month-end")
    args = ap.parse_args()

    changes, other = load_changes()
    ftd = load_ftd()
    named_ids = load_ftd_names()                            # dated SEC names + 13(f) names, for naming only
    n13f = load_13f(named_ids)
    lists = load_fund_lists()
    start = {r[0] for r in db_rows(args.dsn, "select symbol from usmarket.index_members_on(%s, %s)", (INDEX, FIRST))}
    end = {r[0] for r in db_rows(args.dsn, "select symbol from usmarket.index_members_on(%s, %s)", (INDEX, LAST))}
    if len(start) < 490 or len(end) < 490:
        raise SystemExit(f"run build_sp500_membership.py and build_sp500_modern.py first "
                         f"({len(start)} members on {FIRST}, {len(end)} on {LAST})")
    display = {key(s): s for s in start | end}
    known = defaultdict(set)                 # ticker -> company names S&P printed for it
    own = [s[0] for s in SOURCES]               # never read back this build's own rows
    for sym, co in db_rows(args.dsn, """select symbol, company from usmarket.index_change_event
                                        where index_type = %s and source <> all(%s)
                                        union select symbol, company from usmarket.index_constituent_list
                                        where symbol is not null and as_of_date < '2010-01-01' and source <> all(%s)""",
                           (INDEX, own, own)):
        known[key(sym)].add(co)
    for c in changes:
        known[key(c.symbol)].add(c.company)
    # Around a ticker change S&P listed, the new ticker also answers to the old company name
    # (funds printed "Stilwell Financial" for Janus, JNS). Dated: S was Sears before it was Sprint.
    dated_names = []
    if TICKER_CHANGES.exists():
        for r in csv.DictReader(TICKER_CHANGES.open()):
            if r["new_symbol"] and r["old_company"] and r["effective_date"]:
                eff = date.fromisoformat(r["effective_date"])
                dated_names.append((key(r["new_symbol"]), r["old_company"], eff - timedelta(days=10),
                                    eff + timedelta(days=NAME_WINDOW)))
        if "." in c.symbol or key(c.symbol) not in display:
            display[key(c.symbol)] = c.symbol
    log(f"start {FIRST}: {len(start)} members; end {LAST}: {len(end)}; S&P changes {len(changes)} dated, "
        f"{len(other)} other rows; fund lists {len(lists)}; CUSIPs in fails data {len(ftd)}; 13(f) names {n13f}")

    # Changes without an S&P notice, from the reconciliation (NO_NOTICE).
    for d, action, sym, co, how, url in NO_NOTICE:
        changes.append(Change(date.fromisoformat(d), action, sym, co, None, url,
                              f"Not on S&P's surviving pages; {how}", SOURCE_PRESS if url else SOURCE_FUNDS))
        known[key(sym)].add(co)

    # Ticker changes: S&P's, the SEC's (same CUSIP, new ticker), and NO_NOTICE_RENAMES.
    renames = []
    if TICKER_CHANGES.exists():
        for r in csv.DictReader(TICKER_CHANGES.open()):
            if r["effective_date"] and r["old_symbol"] and r["new_symbol"] and key(r["old_symbol"]) != key(r["new_symbol"]):
                renames.append((on_or_after(date.fromisoformat(r["effective_date"])), key(r["old_symbol"]),
                                key(r["new_symbol"]), f"S&P ({r['release_url']})"))
    have = {(o, n) for _, o, n, _ in renames}
    renames += [r for r in ftd_renames(ftd) if (r[1], r[2]) not in have]
    renames += [(date.fromisoformat(d), key(o), key(n), f"No S&P notice found; {why}") for o, n, d, why in NO_NOTICE_RENAMES]

    steps: dict[date, list[tuple]] = defaultdict(list)
    for c in changes:
        if FIRST < c.effective <= LAST:
            steps[c.effective].append((c.action, key(c.symbol), None))
    for d, o, n, _ in renames:
        steps[d].append(("rename", o, n))
    order = {"exclude": 0, "rename": 1, "include": 2}
    for d in steps:
        steps[d].sort(key=lambda st: order[st[0]])

    # Roll forward from the start list.
    m = {key(s) for s in start}
    snaps: dict[date, frozenset] = {}
    contradictions, applied_renames, aliased = [], [], []
    for d in sorted(steps):
        for op, k, new in steps[d]:
            if op == "rename":
                if k in m:
                    if new in m:
                        contradictions.append((d, f"rename {k}->{new}: {new} already a member"))
                    m.discard(k)
                    m.add(new)
                    applied_renames.append((d, k, new))
            elif op == "include":
                if k in m:
                    contradictions.append((d, f"include {k}: already a member"))
                m.add(k)
            else:
                if k not in m:
                    # S&P printed the ticker the member had before a rename (Safeco SAF after the
                    # SEC shows SAFC; Ciena CIEN while it traded as CIEND): follow that rename.
                    via = next((n for d2, o, n in reversed(applied_renames) if o == k and n in m), None)
                    if via:
                        aliased.append((d, f"S&P's exclude {k} read as {via} (renamed earlier)"))
                        k = via
                    else:
                        contradictions.append((d, f"exclude {k}: not a member"))
                m.discard(k)
        snaps[d] = frozenset(m)
    first_state = frozenset(key(s) for s in start)
    kept, last = {}, first_state             # a snapshot only where the membership changed
    for d in sorted(snaps):
        if snaps[d] != last:
            kept[d] = last = snaps[d]
    snaps = kept

    def state_on(d: date) -> frozenset:
        ds = [x for x in snaps if x <= d]
        return snaps[max(ds)] if ds else first_state

    # Fund month-ends: the list at the close of p against the roll effective the next trading day.
    namer = Namer(named_ids, known, dated_names, [(d, o, n) for d, o, n, _ in renames])
    results = []
    for (fund, p) in sorted((fp for fp in lists if FIRST <= fp[1] < date(2010, 1, 1)), key=lambda fp: (fp[1], fp[0])):
        eff = next_trading_day(p)
        roll = state_on(eff)
        named, missing, extra, unnamed, excused = check_list(namer, lists[(fund, p)], roll, eff)
        results.append((p, fund, len(lists[(fund, p)]), named, missing, extra, unnamed, excused))
    exact = sum(1 for r in results if not r[4] and not r[5] and not r[6])
    log(f"   (lines excused as another share class of a member or a label of the same CUSIP: "
        f"{sum(len(r[7]) for r in results)})")
    log(f"fund month-ends matching the roll exactly: {exact} of {len(results)}")
    names_by = {(f, p): {ln: n for ln, n, _ in lists[(f, p)]} for f, p in lists}
    for p, fund, n, named, missing, extra, unnamed, _ in results:
        if missing or extra or unnamed:
            nm = names_by[(fund, p)]
            log(f"   {p} {fund:<6} lines {n} roll {len(state_on(next_trading_day(p)))}  "
                f"fund-only {[(missing[ln], nm[ln][:28]) for ln in list(missing)[:args.show]]}  "
                f"roll-only {extra[:args.show]}  unnamed {[x[1][:30] for x in unnamed[:args.show]]}")

    confirmed, suspects, explained = classify(results, steps, applied_renames)

    final = state_on(LAST)
    end_k = {key(s) for s in end}
    log(f"roll on {LAST} vs build_sp500_modern.py's list: roll-only {sorted(final - end_k)}, "
        f"modern-only {sorted(end_k - final)}")
    log(f"snapshots {len(snaps)}; contradictions {len(contradictions)}; renames applied {len(applied_renames)}; "
        f"S&P tickers read through a rename: {aliased}")
    for c in contradictions:
        log(f"   contradiction {c[0]} {c[1]}")
    if args.dry_run:
        log("dry run: nothing written")
        return 0
    return write(args.dsn, changes, snaps, results, contradictions, applied_renames, renames, display, lists,
                 final == end_k, sorted(final - end_k), sorted(end_k - final), confirmed, suspects, explained)


def write(dsn, changes, snaps, results, contradictions, applied_renames, renames, display, lists,
          end_ok, roll_only, modern_only, confirmed, suspects, explained) -> int:
    import psycopg2  # noqa: PLC0415
    from psycopg2.extras import execute_values  # noqa: PLC0415

    show = lambda k: display.get(k, k)  # noqa: E731
    lo, hi = date(2002, 12, 1), date(2010, 1, 1)       # this build's stretch
    eff_of = {next_trading_day(r[0]): r[0] for r in results}
    effs = sorted(eff_of)

    def verified(d: date) -> bool:
        """The fund month-ends on both sides of d are confirmed (see main) and so is the end."""
        before = [x for x in effs if x <= d]
        after = [x for x in effs if x > d]
        return bool(before and eff_of[before[-1]] in confirmed
                    and (eff_of[after[0]] in confirmed if after else end_ok))

    own = [s[0] for s in SOURCES]
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute((HERE / "schema.sql").read_text())
        for t, where in (("index_membership", "effective_date >= %(lo)s and effective_date < %(hi)s"),
                         ("index_membership_coverage", "covered_from > %(first)s and covered_from < %(hi)s"),
                         ("index_membership_reconciliation", "check_date >= %(lo)s and check_date < %(hi)s"),
                         ("index_change_event", "source = any(%(own)s)"),
                         ("index_symbol_change", "source = any(%(own)s)"),
                         ("index_constituent_list", "source = any(%(own)s)")):
            cur.execute(f"delete from usmarket.{t} where index_type = %(ix)s and {where}",
                        {"ix": INDEX, "own": own, "lo": lo, "hi": hi, "first": FIRST})
        execute_values(cur, """insert into usmarket.index_source_file
            (source, publisher, kind, path, url, captured_on, note) values %s
            on conflict (source) do update set publisher = excluded.publisher, kind = excluded.kind,
              path = excluded.path, url = excluded.url, captured_on = excluded.captured_on, note = excluded.note""",
            SOURCES)

        ev, seen = [], set()
        for c in changes:
            if not (lo <= c.effective < hi):
                continue
            row = (INDEX, previous_trading_day(c.effective), c.effective, c.action, show(key(c.symbol)))
            if row in seen:
                continue
            seen.add(row)
            ev.append((*row, c.company or "?", c.source, c.note[:2000] or None, c.announced, c.url or None))
        if ev:
            execute_values(cur, """insert into usmarket.index_change_event
                (index_type, after_close_date, effective_date, action, symbol, company, source, note,
                 announced_date, release_url) values %s""", ev)

        why = {(d, o, n): note for d, o, n, note in renames}
        sc = [(INDEX, d, show(o), show(n), "", SOURCE_PRESS if why[(d, o, n)].startswith("S&P") else
               SOURCE_FUNDS if why[(d, o, n)].startswith("No S&P") else SOURCE_FTD, why[(d, o, n)][:2000])
              for d, o, n in applied_renames if lo <= d < hi]
        if sc:
            execute_values(cur, """insert into usmarket.index_symbol_change
                (index_type, effective_date, old_symbol, new_symbol, company, source, note) values %s
                on conflict do nothing""", sc)

        rows, line = [], 0
        for p, fund, n, named, missing, extra, unnamed, _ in results:
            basis = f"{fund} holdings at {p} close (SEC filing); names matched to tickers via SEC fails data"
            for ln, name, section in lists[(fund, p)]:
                line += 1
                rows.append((SOURCE_FUNDS, line, INDEX, p, basis, show(named[ln]) if ln in named else None,
                             name, section, None, None, 1))
        execute_values(cur, """insert into usmarket.index_constituent_list
            (source, line_no, index_type, as_of_date, as_of_basis, symbol, company, industry, cusip, isin,
             fund_count) values %s""", rows, page_size=5000)

        mrows = []
        for d, m in snaps.items():
            if lo <= d < hi:
                v = verified(d)
                mrows += [(INDEX, d, show(k), "sp_press_2003_2009:roll_from_2002-11-29", v) for k in sorted(m)]
        execute_values(cur, """insert into usmarket.index_membership
            (index_type, effective_date, symbol, source, is_verified) values %s""", mrows, page_size=5000)

        execute_values(cur, "insert into usmarket.index_membership_coverage values %s", [
            (INDEX, FIRST + timedelta(days=1), LAST - timedelta(days=1),
             "S&P's 2003-2009 notices (and listed no-notice changes) rolled from 29 Nov 2002, checked against "
             "index funds' SEC holdings at each month-end and against the 4 Jan 2010 list")])

        recon = []
        for p, fund, n, named, missing, extra, unnamed, excused in results:
            nm = {ln: nme for ln, nme, _ in lists[(fund, p)]}
            ok = not missing and not extra and not unnamed
            recon.append((INDEX, f"fund_month_end_{fund}", p, ok, n, n - len(missing) - len(unnamed) + len(extra),
                          [show(t) for t in missing.values()], [show(k) for k in extra],
                          f"{fund} at {p} close vs the roll effective {next_trading_day(p)}. missing = fund holds, "
                          f"roll lacks; extra = roll has, fund lacks. "
                          + (f"Fund lines naming no ticker: {[x[1] for x in unnamed]}. " if unnamed else "")
                          + (f"Fund names: {[nm[ln] for ln in missing]}. " if missing else "")
                          + (f"Explained: {excused}" if excused else "")))
        grouped = defaultdict(list)
        for d, msg in contradictions:
            grouped[d].append(msg)
        recon += [(INDEX, "roll_forward", d, False, None, None, [], [], "; ".join(v)) for d, v in grouped.items()]
        # S&P sometimes deletes a member and names its replacement days later (Fannie Mae and
        # Freddie Mac, Sep 2008): the count dips below 500 on S&P's own dates.
        steps_on = defaultdict(list)
        for c in changes:
            steps_on[c.effective].append(c.action)
        short_since = None                     # the S&P day that took the count below 500
        for d, m in sorted(snaps.items()):
            net = steps_on[d].count("include") - steps_on[d].count("exclude")
            if len(m) >= 500:
                short_since = None
            elif short_since is None and net < 0:
                short_since = d
            if lo <= d < hi and len(m) != 500:
                ok = len(m) < 500 and short_since is not None
                recon.append((INDEX, "member_count", d, ok, 500, len(m), [], [],
                              f"S&P deleted more members than it added on {short_since}; the count returns to 500 "
                              f"when S&P names the replacement" if ok
                              else "Count off 500 that S&P's changes do not explain"))
        recon += month_end_status(INDEX, results, confirmed, explained)
        recon.append((INDEX, "cross_fund_suspects", date(2009, 12, 30), not suspects, 0, len(suspects), [], [],
                      "Members no fund list held within 45 days, and non-members every fund list held, "
                      "2002-12 to 2009-12: " + ("; ".join(f"{d}: {m}" for d, m in suspects) if suspects else "none")))
        recon.append((INDEX, "end_vs_2010_list", date(2009, 12, 31), end_ok, None, None,
                      [display.get(k, k) for k in modern_only], [display.get(k, k) for k in roll_only],
                      f"Roll on {LAST} vs build_sp500_modern.py's {LAST} list. missing = modern list has, roll "
                      f"lacks; extra = roll has, modern list lacks"))
        execute_values(cur, """insert into usmarket.index_membership_reconciliation
            (index_type, check_name, check_date, reconciled, expected, actual, missing, extra, note) values %s""",
            recon)
    log(f"wrote {len(mrows)} membership rows ({sum(r[4] for r in mrows)} verified), {len(ev)} change rows, "
        f"{len(sc)} ticker changes, {len(rows)} fund-list rows, {len(recon)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
