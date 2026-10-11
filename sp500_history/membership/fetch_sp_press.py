#!/usr/bin/env python3
"""S&P 500 constituent changes 2010-2026 from S&P Dow Jones Indices' own press releases.

THE SOURCES (S&P's own text only; RESEARCH.md §1 "S&P's own change notices")
-----------
* S&P Global's press archive, Jan 2012 onward:
  ``https://press.spglobal.com/index.php?s=2429&l=100&o=<0,100,...>``. Every release whose
  headline looks like an index change is fetched; the body decides whether the S&P 500
  is touched (a member moving down to the MidCap 400 can sit under a MidCap headline).
* PR Newswire's organisation pages, which carry the same releases: "Standard & Poor's"
  (Jan 2010 - Nov 2011) and "S&P Indices" (Sep 2011 - Jul 2012) for the years before the
  archive; "S&P Dow Jones Indices" (Jul 2012 on) only to catch releases the archive lacks.
  A PR Newswire release with the same headline within two days of an archive release is
  the same release and is skipped.
* Wikipedia and vendor lists are NOT read here. They were used once, afterwards, to look
  for announcements this list missed (see the final report of the 2026-10-12 build).

Every page is cached under ``sp500_history/downloads/sp_press/`` (git-ignored):
``archive/`` and ``prn_list/`` listings, ``release/`` and ``prn_release/`` releases.
A rerun reads the cache and fetches only what is missing (< 2 requests a second).

THE METHOD
----------
1. Each release's S&P 500 rows come from its summary table, in either layout:
   2010-2019 "S&P 500 INDEX - <date>" sections with ADDED/DELETED rows (names only), or
   2019 onward "Effective Date | Index Name | Action | Company Name | Ticker" rows.
   Cells are located by content, since S&P's colspans shift the columns; a blank date or
   action cell repeats the one above.
2. Tickers and exchanges come from S&P's prose, "Name Inc. (NYSE: XYZ)". One row per
   ticker, so "(NASD: FOXAV; FOXBV)" gives two rows. Quarterly-rebalance releases print
   no exchanges; those rows say so in ``note``.
3. ``effective_date`` is the first trading day of the new composition: S&P's "prior to
   the open on D" gives D; "after the close on D" (the 2010-2012 wording) gives the next
   NYSE trading day. The open/close wording is read from the row's own sentence, else
   from the release. A date without a year takes the first year not before the release.
4. "TBA" / "a date to be announced" gives ``status=date_tbd``. A later release about the
   same security and action, sent before the earlier change took effect, makes the
   earlier row ``superseded`` (its note names the later URL). Releases whose S&P 500
   changes are in prose only, or that postpone or cancel a change, are read by hand in
   ``HAND_ROWS`` / ``ROW_FIXES`` below, each tied to a quoted S&P sentence.
5. Nothing is guessed: a missing ticker, exchange or date stays empty and ``note`` says
   which.

Usage:
    python3 sp500_history/membership/fetch_sp_press.py             # fetch what is missing, write the CSV
    python3 sp500_history/membership/fetch_sp_press.py --offline   # cached pages only
    python3 sp500_history/membership/fetch_sp_press.py --refresh-archive   # re-read the listings
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CACHE = REPO / "sp500_history/downloads/sp_press"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
ARCHIVE_URL = "https://press.spglobal.com/index.php?s=2429&l=100&o={o}"
MIN_GAP = 0.6  # seconds between live requests (< 2 a second)

_last = [0.0]
OFFLINE = [False]  # --offline: use cached pages only


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch(url: str, path: Path, refresh: bool = False) -> str | None:
    """Return the page at url, from path when cached, else live (and cache it)."""
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8", errors="replace")
    if OFFLINE[0]:
        return None
    wait = MIN_GAP - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read().decode("utf-8", errors="replace")
            _last[0] = time.time()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            return body
        except (urllib.error.URLError, TimeoutError) as e:
            _last[0] = time.time()
            log(f"  fetch failed ({attempt + 1}/3) {url}: {e}")
            time.sleep(3 * (attempt + 1))
    return None


def cache_name(url: str) -> str:
    """A short, stable file name for a release URL."""
    slug = re.sub(r"[^A-Za-z0-9-]+", "_", url.split("://", 1)[-1].split("/", 1)[-1])[:120]
    return f"{slug}_{hashlib.sha1(url.encode()).hexdigest()[:8]}.html"


ITEM_RE = re.compile(
    r'<div class="wd_date">([^<]+)</div>\s*<div class="wd_title"><a href="([^"]+)">(.*?)</a>', re.S)


def archive_items(page: str) -> list[tuple[str, str, str]]:
    """(date text, url, title) for each release listed on one archive page."""
    return [(d.strip(), html.unescape(u), html.unescape(re.sub(r"<[^>]+>", "", t)).strip())
            for d, u, t in ITEM_RE.findall(page)]


def crawl_archive(refresh: bool) -> list[tuple[str, str, str]]:
    items, o = [], 0
    while True:
        page = fetch(ARCHIVE_URL.format(o=o), CACHE / "archive" / f"o{o:05d}.html", refresh)
        got = archive_items(page or "")
        if not got:
            break
        items += got
        o += 100
    log(f"S&P archive: {len(items)} releases listed, {o // 100} pages")
    return items


# PR Newswire organisation pages that carry S&P's index releases (100 per page).
PRN = "https://www.prnewswire.com"
PRN_ORGS = [  # cache prefix, org page
    ("sp", "/news/standard-%26-poor%27s/"),          # Jan 2010 - Nov 2011 (index releases)
    ("spi", "/news/s%26p-indices/"),                  # Sep 2011 - Jul 2012
    ("spdji", "/news/s%26p-dow-jones-indices/"),      # Jul 2012 onward (gap check only)
]
PRN_ITEM_RE = re.compile(r'href="(/news-releases/[^"]+-\d+\.html)".*?<small>([^<]*ET)</small>\s*(.*?)\s*</h3>', re.S)


def prn_items(page: str) -> list[tuple[str, str, str]]:
    out = []
    for u, d, t in PRN_ITEM_RE.findall(page):
        title = html.unescape(re.sub(r"<[^>]+>|\s+", " ", t)).strip()
        out.append((d[:12], PRN + u, title))
    return out


def crawl_prn(refresh: bool) -> list[tuple[str, str, str]]:
    items = []
    for prefix, org in PRN_ORGS:
        n = 1
        while True:
            page = fetch(f"{PRN}{org}?page={n}&pagesize=100",
                         CACHE / "prn_list" / f"{prefix}_p{n}.html", refresh)
            got = prn_items(page or "")
            if not got:  # the empty page past the end stays cached too
                break
            items += got
            n += 1
    log(f"PR Newswire: {len(items)} releases listed")
    return items


# A release can carry S&P 500 lines under a MidCap/SmallCap headline (a member moving
# down), so every index-change headline is fetched and the body decides.
INDEX_TITLE = re.compile(r"S&P 500|S&P 100\b|MidCap|SmallCap|Composite 1500|\bJoin|U\.S\. Indices"
                         r"|Constituent|Replace|Rebalanc|S&P 900|S&P 1500|U\.S\. Ind|Treatment of|Index Change", re.I)
NOT_INDEX = re.compile(r"Case-Shiller|Experian|Sustainability|Launch|SPIVA|Platts|Board|Buyback|"
                       r"Dividend (?:Aristocrat|Payment|Increase|Growth|Rate)|Indicated Dividend|Earnings|Pension|"
                       r"Joins (?:S&P Global|S&P Capital|LCD|Project|Cyber|Climate|with|the Net|Coalition)", re.I)


def is_index_title(title: str) -> bool:
    return bool(INDEX_TITLE.search(title)) and not NOT_INDEX.search(title)


# NYSE full-day closures 2010-2027 (weekdays only).
NYSE_CLOSED = {date.fromisoformat(d) for d in """
2010-01-01 2010-01-18 2010-02-15 2010-04-02 2010-05-31 2010-07-05 2010-09-06 2010-11-25 2010-12-24
2011-01-17 2011-02-21 2011-04-22 2011-05-30 2011-07-04 2011-09-05 2011-11-24 2011-12-26
2012-01-02 2012-01-16 2012-02-20 2012-04-06 2012-05-28 2012-07-04 2012-09-03 2012-10-29 2012-10-30
2012-11-22 2012-12-25 2013-01-01 2013-01-21 2013-02-18 2013-03-29 2013-05-27 2013-07-04 2013-09-02
2013-11-28 2013-12-25 2014-01-01 2014-01-20 2014-02-17 2014-04-18 2014-05-26 2014-07-04 2014-09-01
2014-11-27 2014-12-25 2015-01-01 2015-01-19 2015-02-16 2015-04-03 2015-05-25 2015-07-03 2015-09-07
2015-11-26 2015-12-25 2016-01-01 2016-01-18 2016-02-15 2016-03-25 2016-05-30 2016-07-04 2016-09-05
2016-11-24 2016-12-26 2017-01-02 2017-01-16 2017-02-20 2017-04-14 2017-05-29 2017-07-04 2017-09-04
2017-11-23 2017-12-25 2018-01-01 2018-01-15 2018-02-19 2018-03-30 2018-05-28 2018-07-04 2018-09-03
2018-11-22 2018-12-05 2018-12-25 2019-01-01 2019-01-21 2019-02-18 2019-04-19 2019-05-27 2019-07-04
2019-09-02 2019-11-28 2019-12-25 2020-01-01 2020-01-20 2020-02-17 2020-04-10 2020-05-25 2020-07-03
2020-09-07 2020-11-26 2020-12-25 2021-01-01 2021-01-18 2021-02-15 2021-04-02 2021-05-31 2021-07-05
2021-09-06 2021-11-25 2021-12-24 2022-01-17 2022-02-21 2022-04-15 2022-05-30 2022-06-20 2022-07-04
2022-09-05 2022-11-24 2022-12-26 2023-01-02 2023-01-16 2023-02-20 2023-04-07 2023-05-29 2023-06-19
2023-07-04 2023-09-04 2023-11-23 2023-12-25 2024-01-01 2024-01-15 2024-02-19 2024-03-29 2024-05-27
2024-06-19 2024-07-04 2024-09-02 2024-11-28 2024-12-25 2025-01-01 2025-01-09 2025-01-20 2025-02-17
2025-04-18 2025-05-26 2025-06-19 2025-07-04 2025-09-01 2025-11-27 2025-12-25 2026-01-01 2026-01-19
2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03 2026-09-07 2026-11-26 2026-12-25 2027-01-01""".split()}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_CLOSED


def next_trading_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------- release text

BODY_START = ("wd_body wd_news_body", "release-body")
BODY_END = re.compile(r"ABOUT S&(?:amp;)?P DOW JONES|About S&(?:amp;)?P (?:Dow Jones )?Indices|About S&(?:amp;)?P Global|"
                      r"FOR MORE INFORMATION|For more information about S&(?:amp;)?P|About Standard &(?:amp;)? Poor",
                      re.I)


def body_html(page: str) -> str:
    """The release text (HTML) between the dateline and S&P's boilerplate."""
    i = max((page.find(m) for m in BODY_START), default=-1)
    if i < 0:
        return ""
    i = page.find(">", i) + 1
    m = BODY_END.search(page, i)
    return page[i:m.start() if m else i + 60000]


def plain(fragment: str) -> str:
    t = re.sub(r"<br\s*/?>|</p>|</tr>|</td>|</li>", " ", fragment, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def tables(fragment: str) -> list[list[list[str]]]:
    """Every <table> as rows of cell texts, rowspans and colspans expanded."""
    out = []
    for tb in re.findall(r"<table.*?</table>", fragment, re.S | re.I):
        rows, carry = [], {}  # carry: column -> (rows left, text)
        for tr in re.findall(r"<tr.*?</tr>", tb, re.S | re.I):
            row, col = [], 0
            cells = re.findall(r"<t([dh])([^>]*)>(.*?)</t[dh]>", tr, re.S | re.I)
            for _, attrs, inner in cells:
                while col in carry:
                    left, txt = carry[col]
                    row.append(txt)
                    carry[col] = (left - 1, txt)
                    if left - 1 == 0:
                        del carry[col]
                    col += 1
                txt = plain(inner)
                rs = int((re.search(r'rowspan="?(\d+)', attrs) or [0, 1])[1])
                cs = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1])
                for _ in range(cs):
                    if rs > 1:
                        carry[col] = (rs - 1, txt)
                    row.append(txt)
                    col += 1
            while col in carry:
                left, txt = carry[col]
                row.append(txt)
                carry[col] = (left - 1, txt)
                if left - 1 == 0:
                    del carry[col]
                col += 1
            if any(row):
                rows.append(row)
        out.append(rows)
    return out


EXCH = r"NYSE\s*(?:Arca|MKT|American|Amex)?|NASDAQ(?:\s*GS|\s*GM)?|Nasdaq(?:\s*GS|\s*GM)?|NASD|NasdaqGS|AMEX|Amex|BATS|Cboe\s*BZX|CBOE"
TICK = r"[A-Z][A-Za-z0-9.\-/]{0,9}(?: ?wi)?"
MENTION = re.compile(r"\(\s*(" + EXCH + r")\s*:\s*(" + TICK + r"(?:\s*[;,]\s*(?:" + EXCH + r")?\s*:?\s*" + TICK + r")*)\s*\)")


def split_tickers(s: str) -> list[str]:
    """'FOXAV; FOXBV' -> ['FOXAV', 'FOXBV'] (one row per share class)."""
    out = [re.sub(r"^(?:" + EXCH + r")\s*:\s*", "", t.strip()) for t in re.split(r"[;,]", s) if t.strip()]
    return [p for t in out for p in (t.split("/") if re.fullmatch(r"[A-Z]{2,}/[A-Z]{2,}", t) else [t])]


def norm_exchange(x: str) -> str:
    x = re.sub(r"\s+", " ", x).strip()
    return {"Nasdaq": "NASDAQ", "NASD": "NASDAQ", "NasdaqGS": "NASDAQ", "Amex": "AMEX"}.get(x, x.upper() if x.lower().startswith("nasdaq") else x)


def mentions(text: str) -> list[tuple[int, str, str]]:
    """(position, exchange, ticker) for each '(NYSE: XYZ)' in the text."""
    return [(m.start(), norm_exchange(m.group(1)), t) for m in MENTION.finditer(text)
            for t in split_tickers(m.group(2))]


# ---------------------------------------------------------------- S&P 500 rows

MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
DATE_RE = re.compile(r"(?:(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+)?"
                     r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})"
                     r"(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?", re.I)
DATE2_RE = re.compile(r"\b(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d\d)\b", re.I)
TBA_RE = re.compile(r"^\s*(TBA|TBD|To be (?:announced|determined))\s*$", re.I)


@dataclass
class Event:
    action: str           # include | exclude
    symbol: str
    company: str
    date_raw: str          # as printed by S&P (table cell or prose)
    exchange: str = ""
    timing: str = ""       # open | close | ""
    effective: date | None = None
    status: str = "ok"
    note: str = ""
    flags: list[str] = field(default_factory=list)
    table_row: str = ""


def parse_date(raw: str, announced: date) -> tuple[date | None, str]:
    """A date printed by S&P; the year, when missing, is the first that is not
    before the announcement. Returns (date, problem)."""
    m2 = DATE2_RE.search(raw or "")
    if m2:
        raw = f"{m2.group(2)} {m2.group(1)}, 20{m2.group(3)}"
    m = DATE_RE.search(raw or "")
    if not m:
        return None, f"no date in '{raw}'"
    wd, mon, day, yr = m.groups()
    mon_n, day_n = MONTHS[mon[:3].lower()], int(day)
    years = [int(yr)] if yr else [announced.year, announced.year + 1]
    for y in years:
        try:
            d = date(y, mon_n, day_n)
        except ValueError:
            return None, f"impossible date '{raw}'"
        if yr or d >= announced - timedelta(days=5):
            break
    if wd and d.strftime("%A")[:3].lower() != wd[:3].lower():
        return d, f"weekday '{wd}day' does not match {d}"
    return d, ""


ACTION = {"addition": "include", "add": "include", "added": "include", "deletion": "exclude",
          "delete": "exclude", "deleted": "exclude", "drop": "exclude", "dropped": "exclude",
          "removal": "exclude", "removed": "exclude"}


def is_sp500(cell: str) -> bool:
    """'S&P 500'; also S&P's own typo 'S&P MIDCAP 500' (2015-09-30, 2018-06-04 tables)."""
    return bool(re.fullmatch(r"S&P\s*(?:MidCap\s*)?500\*?(?:\s*Index)?", cell.strip(), re.I))


INDEX_CELL = re.compile(r"S&P\s*(?:500|MidCap\s*400|SmallCap\s*600|100|Composite\s*1500|400|600)\*?", re.I)
TICKER_CELL = re.compile(r"[A-Z][A-Za-z0-9.\-/]{0,9}")


def modern_row(row: list[str]) -> tuple[str, str, str, str] | None:
    """(index, action word, company, ticker) from one summary-table row, located by
    content because S&P's colspans shift the columns from one release to the next."""
    i = next((k for k, c in enumerate(row) if INDEX_CELL.fullmatch(c.strip())), None)
    if i is None:
        return None
    a = next((k for k in range(i + 1, len(row)) if row[k].strip().lower() in ACTION), None)
    if a is None:
        return None
    rest = [c.strip() for c in row[a + 1:] if c.strip() and c.strip() != row[a].strip()]
    if not rest:
        return None
    company, ticker = rest[0], ""
    for c in rest[1:]:
        if TICKER_CELL.fullmatch(c) and c != company or TICKER_CELL.fullmatch(c) and company.isupper():
            ticker = c
            break
    return row[i].strip(), row[a].strip(), company, ticker


SECTION_RE = re.compile(r"(S&P[\w &]*?)\s*(?:INDEX(?:ES)?)?\s*[\u2013\u2014-]+\s*(.*\d.*|TBA|TBD)$", re.I)


def table_events(tbs: list[list[list[str]]]) -> list[Event]:
    """S&P 500 rows from the summary tables, both layouts. A blank date cell repeats
    the date above it, as S&P lays the tables out."""
    out = []
    for tb in filter(None, tbs):
        head = " ".join(tb[0]).lower()
        if "index name" in head and "action" in head:          # 2012 onward
            last_date = ""
            for row in tb[1:]:
                first = row[0].strip() if row else ""
                if DATE_RE.search(first) or DATE2_RE.search(first) or TBA_RE.match(first):
                    last_date = first
                got = modern_row(row)
                if got and is_sp500(got[0]):
                    out.append(Event(ACTION[got[1].lower()], got[3], got[2], last_date,
                                     table_row=" | ".join(c for c in row if c)))
        else:                                                   # 2010-2019: a section per index
            section, act = None, None
            for row in tb:
                m = SECTION_RE.match(row[0].strip()) if row else None
                if m:
                    section, act = (m.group(1).strip(), m.group(2).strip()), None
                    continue
                if len(row) < 2 or row[1].strip().upper() == "COMPANY":
                    continue
                if row[0].strip():  # a blank action cell repeats the one above
                    act = ACTION.get(row[0].strip().lower())
                if act and section and is_sp500(section[0]) and row[1].strip():
                    out.append(Event(act, "", row[1].strip(), section[1],
                                     table_row=f"S&P 500 INDEX - {section[1]} | {act} | {row[1]}"))
    return out


def sentences(text: str) -> list[str]:
    return re.split(r"(?<=[a-z0-9)\]])(?<!\bBros)(?<!\bSt)(?<!\bJr)(?<!\bMt)(?<!\bvs)\.\s+(?=[A-Z])", text)


def name_key(name: str) -> str:
    n = re.sub(r"[^a-z0-9& ]", " ", name.lower())
    n = re.sub(r"\b(inc|corp|corporation|co|company|ltd|plc|the|holdings?|group|class [a-c])\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


NOT_A_SUFFIX = re.compile(r"\b(?:will|is|was|are|were|has|have|had|replac\w*|join\w*|added|remov\w*|"
                          r"delet\w*|acquir\w*|spin\w*|in|on|to|from|by|which)\b|[;:]")


def ticker_for_name(name: str, text: str) -> tuple[str, str]:
    """(exchange, tickers) of the first '(EXCH: TICK)' after S&P's short table name.
    First pass: only a legal suffix ("Inc.", "Corp.", "plc") in between. Second pass:
    any words that are not a verb or preposition ("E. I. du Pont de Nemours and Co.")."""
    name = re.sub(r"\s*\(.*?\)", "", name)
    key = (re.escape(name.strip()).replace("\\ ", "\\s*").replace("\\-", "-\\s*")
           .replace("\\.", "\\.\\s*"))
    for strict in (True, False):
        for m in re.finditer(key, text, re.I):
            tail = text[m.end():m.end() + 70]
            mm = MENTION.search(tail)
            if not mm:
                continue
            between = tail[:mm.start()]
            if "(" in between:
                continue
            if strict and re.search(r"\b(?!plc\b|inc\b|corp\b|co\b|ltd\b|nv\b|llc\b)[a-z]{2,}\b", between):
                continue
            if not strict and NOT_A_SUFFIX.search(between):
                continue
            return norm_exchange(mm.group(1)), mm.group(2).strip()
    return fuzzy_ticker(name, text)


def fuzzy_ticker(name: str, text: str) -> tuple[str, str]:
    """Third pass, for a table name S&P spelled differently in the prose ("Ryder
    Systems" / "Ryder System Inc."): the mention whose preceding words contain the
    name's first word and at least 60% of its words."""
    want = [w.rstrip("s") for w in name_key(name).split()]
    best, score = ("", ""), 0.0
    for m in MENTION.finditer(text):
        window = re.split(r"\swill\s|\sin the\s|\)", text[max(0, m.start() - 90):m.start()])[-1]
        have = {w.rstrip("s") for w in name_key(window).split()}
        if not want or want[0] not in have:
            continue
        sc = sum(w in have for w in want) / len(want)
        if sc > score:
            best, score = (norm_exchange(m.group(1)), m.group(2).strip()), sc
    return best if score >= 0.6 else ("", "")


def exchange_for_ticker(sym: str, text: str) -> str:
    base = re.sub(r"(?i)\s*wi$", "", sym)
    for _, ex, t in mentions(text):
        if t.upper() == sym.upper() or re.sub(r"(?i)\s*wi$", "", t).upper() == base.upper():
            return ex
    return ""


DATELINE = re.compile(r"^.{0,60}?/\s*PRNewswire(?:-FirstCall)?\s*/\s*--\s*", re.I)


def key_sentence(ev: Event, sents: list[str]) -> str:
    """The sentence of S&P's text that announces this change (dateline dropped)."""
    return DATELINE.sub("", _key_sentence(ev, sents))


def _key_sentence(ev: Event, sents: list[str]) -> str:
    probes = [p for p in (f": {ev.symbol})", f":{ev.symbol})", f": {ev.symbol};", f"; {ev.symbol})", ev.company)
              if p and len(p) > 2]
    for need_500 in (True, False):
        for p in probes:
            for s in sents:
                if p.lower() in s.lower() and (not need_500 or "S&P 500" in s):
                    return s.strip()
    return ""


TIMING_RE = re.compile(r"(after the (?:market )?close|(?:prior to|before) the (?:market )?open|at the (?:market )?open|"
                       r"effective (?:with|as of) the (?:market )?open)[a-z ]{0,30}?\s(?:on|of)\s+([^.;]{0,40})", re.I)


def timing_of(ev: Event, text: str, sent: str) -> str:
    """open | close for this change, from S&P's wording; '' when unclear."""
    def kind(s):
        k = {("close" in t.group(1).lower()) for t in TIMING_RE.finditer(s)}
        return "" if len(k) != 1 else ("close" if k.pop() else "open")
    k = kind(sent)
    if k:
        return k
    if re.search(r"(?:take place|effective) prior to the open(?:ing)? of trading on the effective date", text, re.I):
        return "open"
    k = kind(text)
    if k:
        return k
    close = re.search(r"after the (?:market )?close", text, re.I)
    opn = re.search(r"(?:prior to|before) the (?:market )?open", text, re.I)
    if close and not opn:
        return "close"
    if opn and not close:
        return "open"
    return ""


# Prose, for releases without an S&P 500 summary table (early 2010 used plain-text tables).
M = r"\(\s*(?:" + EXCH + r")\s*:\s*" + TICK + r"(?:\s*[;,]\s*" + TICK + r")*\s*\)"
IN_500 = r"(?:,[^,()]{0,60},)?\s+in the (?:S&P 100 (?:and|&) )?S&P 500(?! GICS)"
REPLACE_RE = re.compile(r"(" + M + r")\s*(?:,[^()]{0,60}?,\s*)?will replace\s+([^()]{1,90}?)\s*(" + M + r")" + IN_500)
REPLACE_NAME_RE = re.compile(r"(" + M + r")\s*(?:,[^()]{0,60}?,\s*)?will replace\s+([A-Z][^()]{0,60}?)" + IN_500)
ADD_RE = re.compile(r"(" + M + r")[^()]{0,40}?\s(?:will be|was|has been) added to the S&P 500(?! GICS)")
ADD2_RE = re.compile(r"will add [^()]{0,60}?(" + M + r") to the S&P 500(?! GICS)")
DROP_RE = re.compile(r"(" + M + r")[^()]{0,40}?\s(?:will be|was|has been) (?:removed|deleted|dropped) from the S&P 500")
MOVE_IN_RE = re.compile(r"will move to the S&P 500,? replacing ((?:[^()]{1,80}?" + M + r"[, and]*)+)")


def prose_name(text: str, end: int) -> str:
    """The company name printed just before position end ('... constituent Name Inc.')."""
    head = text[max(0, end - 120):end]
    head = re.split(r"constituents?\s|:\s|;\s|--\s|\.\s(?=[A-Z])|,\s+and\s|\sand\s(?=[A-Z])|,\s(?=[A-Z][^,]*$)|\sadd\s", head)[-1]
    return head.strip(" ,")


def prose_events(text: str) -> list[Event]:
    """S&P 500 changes stated in sentences: 'A (NYSE: A) will replace B (NYSE: B) in the
    S&P 500', '... will be added to / removed from the S&P 500', '... will move to the
    S&P 500, replacing B (..), C (..)'. Date and timing are read later per sentence."""
    out = []
    for sent in sentences(text):
        if "S&P 500" not in sent:
            continue
        for m in REPLACE_RE.finditer(sent):
            a, b = MENTION.search(m.group(1)), MENTION.search(m.group(3))
            out.append(Event("include", a.group(2), prose_name(sent, m.start()), "", norm_exchange(a.group(1)), note=sent))
            out.append(Event("exclude", b.group(2), m.group(2).strip(" ,"), "", norm_exchange(b.group(1)), note=sent))
        for m in REPLACE_NAME_RE.finditer(sent):
            a = MENTION.search(m.group(1))
            ex, tk = ticker_for_name(m.group(2), text)
            out.append(Event("include", a.group(2), prose_name(sent, m.start()), "", norm_exchange(a.group(1)), note=sent))
            out.append(Event("exclude", tk, m.group(2).strip(" ,"), "", ex, note=sent))
        for rx, act in ((ADD_RE, "include"), (ADD2_RE, "include"), (DROP_RE, "exclude")):
            for m in rx.finditer(sent):
                a = MENTION.search(m.group(1))
                out.append(Event(act, a.group(2), prose_name(sent, m.start(1)), "", norm_exchange(a.group(1)), note=sent))
        for m in MOVE_IN_RE.finditer(sent):
            for mm in MENTION.finditer(m.group(1)):
                start = m.start(1) + mm.start()
                out.append(Event("exclude", mm.group(2), prose_name(sent, start), "", norm_exchange(mm.group(1)), note=sent))
    return out


def prose_date(ev: Event, text: str) -> str:
    """The date S&P gives for a prose change: in its own sentence, else the release's
    opening 'will make the following changes ... on <date>:' line."""
    for src in (ev.note, sentences(text)[0] if text else ""):
        if re.search(r"date to be announced|TBA\b", src):
            return "TBA"
        t = TIMING_RE.search(src)
        if t and DATE_RE.search(t.group(2)):
            return t.group(0)
    return ""


CHANGE_VERBS = re.compile(r"will replace|will be added|will be removed|will be deleted|will be dropped|"
                          r"will move|will be moved|will join|was added|were added|has been added|"
                          r"replaced .{0,60} in the S&P 500|added to the S&P 500|removed from the S&P 500", re.I)


def release_events(page: str, announced: date) -> tuple[list[Event], list[str]]:
    """Every S&P 500 change in one release, plus problems found while reading it."""
    b = body_html(page)
    text, issues = plain(re.sub(r"<table.*?</table>", " ", b, flags=re.S | re.I)), []
    sents = sentences(text)
    evs = table_events(tables(b))
    prose = prose_events(text)
    if not evs and prose:
        evs = prose
        for ev in evs:
            ev.date_raw = prose_date(ev, text)
            ev.flags.append("read from S&P's prose; no S&P 500 summary table")
    elif not evs and "S&P 500" in text and any("S&P 500" in s and CHANGE_VERBS.search(s) for s in sents):
        issues.append("S&P 500 change wording but no S&P 500 rows found")

    expanded = []
    for ev in evs:
        if not ev.symbol:
            ev.exchange, ev.symbol = ticker_for_name(ev.company, text)
        for t in split_tickers(ev.symbol) or [""]:
            expanded.append(Event(ev.action, t, ev.company, ev.date_raw, ev.exchange, flags=list(ev.flags),
                                  table_row=ev.table_row, note=ev.note))
    evs = expanded
    if prose and evs is not prose and evs[0].table_row:  # self-check: prose and table agree
        tab = {(e.action, e.symbol.upper()) for e in evs}
        for p in prose:
            for t in split_tickers(p.symbol):
                if t and (p.action, t.upper()) not in tab:
                    issues.append(f"prose says {p.action} {t} but the S&P 500 table does not")
    for ev in evs:
        if not ev.symbol:
            ev.flags.append("ticker not in S&P's text")
        if not ev.exchange:
            ev.exchange = exchange_for_ticker(ev.symbol, text)
        ev.note = DATELINE.sub("", ev.note) if ev.note else key_sentence(ev, sents)
        if TBA_RE.match(ev.date_raw):
            ev.status = "date_tbd"
            continue
        ev.timing = timing_of(ev, text, ev.note)
        d, prob = parse_date(ev.date_raw, announced)
        if prob:
            ev.flags.append(prob)
        said = {parse_date(t.group(0), announced)[0] for t in DATE_RE.finditer(text)}
        if d and ev.table_row and d not in said:
            ev.flags.append(f"table date {d} not printed in S&P's text")
        if d and ev.timing == "open":
            ev.effective = d
        elif d and ev.timing == "close":
            ev.effective = next_trading_day(d)
        elif d:
            ev.flags.append("cannot tell open/close")
    return evs, issues


# ---------------------------------------------------------------- assembly

@dataclass
class Release:
    announced: date
    url: str
    title: str
    path: Path


def title_key(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\bthe\b", "", t.lower()))


def release_list(refresh: bool) -> list[Release]:
    """S&P's archive from Jan 2012; PR Newswire before that and for releases the
    archive lacks (a headline at least 90% alike within two days is the same release:
    S&P corrected some headlines, e.g. "Nektar Therapeutics" on 2018-03-09)."""
    out, seen = [], {}
    for d, url, title in crawl_archive(refresh):
        if is_index_title(title):
            ann = datetime.strptime(d, "%b %d, %Y").date()
            out.append(Release(ann, url, title, CACHE / "release" / cache_name(url)))
            seen.setdefault(title_key(title), []).append(ann)
    for d, url, title in crawl_prn(refresh):
        if not is_index_title(title):
            continue
        ann = datetime.strptime(d, "%b %d, %Y").date()
        key = title_key(title)
        if any(abs((ann - x).days) <= 2 and difflib.SequenceMatcher(None, key, k).ratio() > 0.9
               for k, xs in seen.items() for x in xs):
            continue
        out.append(Release(ann, url, title, CACHE / "prn_release" / cache_name(url)))
    return sorted(out, key=lambda r: (r.announced, r.url))


FIELDS = ["announced_date", "effective_date", "action", "symbol", "exchange", "company",
          "release_url", "release_title", "status", "note"]


def to_rows(rel: Release, evs: list[Event]) -> list[dict]:
    rows = []
    for ev in evs:
        flags = list(ev.flags)
        if ev.symbol and not ev.exchange:
            flags.append("exchange not in S&P's text")
        if ev.status == "date_tbd" and TBA_RE.match(ev.date_raw):
            flags.append("S&P: effective date to be announced")
        if ev.symbol.endswith("wi"):
            flags.append("when-issued ticker as printed by S&P")
        note = ev.note or (f"Summary table: {ev.table_row}" if ev.table_row else "")
        if len(note) > 300:
            note = note[:297] + "..."
        if flags:
            note += " [" + "; ".join(flags) + "]"
        rows.append({"announced_date": rel.announced.isoformat(),
                     "effective_date": ev.effective.isoformat() if ev.effective else "",
                     "action": ev.action, "symbol": ev.symbol, "exchange": ev.exchange,
                     "company": ev.company, "release_url": rel.url, "release_title": rel.title,
                     "status": ev.status, "note": note})
    return rows


def security_key(r: dict) -> str:
    return r["symbol"].upper().removesuffix("WI") if r["symbol"] else name_key(r["company"])


def link_superseded(rows: list[dict]) -> None:
    """A later release about the same security and action replaces the earlier one,
    which becomes 'superseded' (its note names the later URL), when it came within 200
    days and no opposite action for that security lies between them. A security cannot
    be added twice without a deletion in between, so this also catches a change whose
    first date passed without effect (Michael Kors: 1 Nov 2013, then 12 Nov 2013)."""
    by = defaultdict(list)
    for r in rows:
        by[security_key(r)].append(r)
    for grp in by.values():
        grp.sort(key=lambda r: (r["announced_date"], r["effective_date"]))
        for i, a in enumerate(grp):
            for b in grp[i + 1:]:
                if b["action"] != a["action"]:
                    if b["release_url"] != a["release_url"] and b["status"] in ("ok", "date_tbd"):
                        break           # an opposite change came first: a stands
                    continue
                if b["release_url"] == a["release_url"]:
                    continue
                gap = (date.fromisoformat(b["announced_date"]) - date.fromisoformat(a["announced_date"])).days
                if gap <= 200:
                    a["status"] = "superseded"
                    a["note"] = f"Superseded by {b['release_url']} . " + a["note"]
                break


def lookup(table: dict, url: str):
    return next((v for k, v in table.items() if url.endswith(k)), None)


def sentence_with(quote: str, page: str) -> str:
    """S&P's full sentence containing quote; fails loudly if S&P's text lacks it."""
    text = plain(re.sub(r"<table.*?</table>", " ", body_html(page), flags=re.S | re.I))
    for s in sentences(text):
        if quote in s:
            return DATELINE.sub("", s.strip())
    raise SystemExit(f"quote not found in S&P's text: {quote!r}")


def hand_events(entries: list[dict], page: str, announced: date) -> list[Event]:
    """Rows read by hand (HAND_ROWS), each tied to a quoted sentence of S&P's text."""
    out = []
    for e in entries:
        ev = Event(e["action"], e.get("symbol", ""), e["company"], e.get("date", ""), e.get("exchange", ""),
                   status=e.get("status", "ok"), note=sentence_with(e["quote"], page),
                   flags=["read by hand"] + e.get("flags", []))
        if not ev.symbol:
            ev.flags.append("ticker not in S&P's text")
        if ev.date_raw and ev.status in ("ok", "postponed"):
            d, prob = parse_date(ev.date_raw, announced)
            if prob:
                ev.flags.append(prob)
            ev.effective = d if e["timing"] == "open" else next_trading_day(d)
        out.append(ev)
    return out


def apply_fixes(url: str, evs: list[Event], page: str) -> None:
    for suffix, match, fields, quote in ROW_FIXES:
        if not url.endswith(suffix):
            continue
        hit = [ev for ev in evs if match in (ev.symbol, ev.company)]
        if not hit:
            raise SystemExit(f"ROW_FIXES: no row {match!r} in {url}")
        for ev in hit:
            for k, v in fields.items():
                setattr(ev, k, v)
            ev.flags = [f for f in ev.flags if not f.startswith("ticker not")]
            ev.flags.append("corrected by hand: " + sentence_with(quote, page))


def build(releases: list[Release]) -> list[dict]:
    rows, issues = [], []
    for rel in releases:
        page = fetch(rel.url, rel.path)
        if page is None:
            issues.append(f"{rel.announced} not fetched {rel.url}")
            continue
        hand = lookup(HAND_ROWS, rel.url)
        if hand is not None:
            evs, probs = hand_events(hand, page, rel.announced), []
        else:
            evs, probs = release_events(page, rel.announced)
            apply_fixes(rel.url, evs, page)
            fixed = {ev.symbol for ev in evs}
            probs = [p for p in probs if not (p.startswith("prose says") and p.split()[3] in fixed)]
        if lookup(NO_SP500_CHANGE, rel.url):
            probs = [p for p in probs if "no S&P 500 rows" not in p]
        rows += to_rows(rel, evs)
        issues += [f"{rel.announced} {rel.title[:70]} | {p} | {rel.url}" for p in probs]
    rows = [r for r in rows if START <= r["announced_date"] <= END]
    rows.sort(key=lambda r: (r["announced_date"], r["release_url"], r["effective_date"], r["action"], r["symbol"]))
    link_superseded(rows)
    for i in issues:
        log("ISSUE " + i)
    return rows


def checks(rows: list[dict]) -> None:
    log("\nrows by status: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r["status"] for r in rows).items())))
    log("year (effective, status ok): include exclude diff")
    per = defaultdict(Counter)
    for r in rows:
        if r["status"] == "ok" and r["effective_date"]:
            per[r["effective_date"][:4]][r["action"]] += 1
    for y in sorted(per):
        inc, exc = per[y]["include"], per[y]["exclude"]
        log(f"  {y}: {inc:3d} {exc:3d} {inc - exc:+d}{'  <-- differs by more than 2' if abs(inc - exc) > 2 else ''}")
    for r in rows:
        if r["status"] == "ok" and (not r["symbol"] or not r["effective_date"]):
            log(f"  incomplete: {r['announced_date']} {r['action']} {r['symbol'] or '?'} {r['company']} {r['release_url']}")


START, END = "2010-01-01", "2026-12-31"

# ---------------------------------------------------------------- read by hand
# Every entry below was read in the cached release and is tied to a quoted S&P sentence
# (the build stops if S&P's text does not contain it). Keys are URL endings.

# Releases whose S&P 500 changes the parser cannot read (share-class lines described in
# prose, changes later cancelled). These rows replace the parsed ones for that release.
CLASS_LINE = "which listed line is the added one is not stated in S&P's text"
HAND_ROWS: dict[str, list[dict]] = {
    "2014-02-03-Treatment-of-Google-Stock-Split-in-the-S-P-100-and-S-P-500": [
        dict(action="include", company="Google Inc. Class C capital stock", date="Wednesday, April 2",
             timing="close", quote="will add the Class C share line to the S&P 100 and S&P 500"),
        dict(action="exclude", company="Google Inc. Class A", date="Friday, June 20", timing="close",
             quote="Effective after the close on June 20, the Class A share line will be dropped"),
    ],
    "Revises-Previously-Announced-Treatment-of-Google-Stock-Split": [
        dict(action="exclude", company="Google Inc. Class A", status="cancelled",
             quote="there will not be a switch from Class A to Class C on June 20th"),
    ],
    "2014-07-30-S-P-Dow-Jones-Indices-Announces-Treatment-of-Stock-Dividend-for-Discovery-Communications-in-S-P-500": [
        dict(action="include", symbol="DISCK", exchange="NASDAQ", company="Discovery Communications Inc. Class C",
             date="Wednesday, August 6", timing="close",
             quote="will add the Class C share line to the S&P 500 effective after the close of trading"),
    ],
    "2022-04-07-S-P-Dow-Jones-Indices-Announces-Treatment-of-AT-T-Transaction-with-Discovery": [
        dict(action=a, symbol=t, exchange="NASDAQ", company=c, status="date_tbd",
             flags=["date not in S&P's text: 'At the time of the transaction'"],
             quote="converted and reclassified into a single share class line")
        for a, t, c in (("exclude", "DISCA", "Discovery Inc. Series A"), ("exclude", "DISCK", "Discovery Inc. Series C"),
                        ("include", "WBD", "Warner Bros. Discovery Inc."))
    ],
    "2015-08-10-S-P-U-S-Indices-Methodology-Update-and-Constituent-Additions": [
        dict(action="include", company=f"{c} (additional listed share class line; S&P prints {t})",
             date="Friday, September 18", timing="close", flags=[CLASS_LINE],
             quote="will each have an additional listed share class line added to the S&P 500")
        for c, t in (("Comcast Corp.", "NASD:CMCSA/CMCSK"), ("Twenty-First Century Fox Inc.", "NASD:FOXA/FOX"),
                     ("News Corp.", "NASD:NWSA/NWS"))
    ],
}

# Corrections to parsed rows: (URL ending, symbol or company as parsed, fields, quote).
ROW_FIXES: list[tuple[str, str, dict, str]] = [
    # The table names the merged company; the prose prints only the pre-merger ticker.
    ("2015-12-28-Willis-Group-Holdings-Set-to-Join-the-S-P-500-Fossil-Group-to-Join-S-P-MidCap-400-Adeptus-Health-to-Join-S-P-SmallCap-600",
     "Willis Towers Watson", {"symbol": "WSH", "exchange": "NYSE"},
     'trade under the ticker symbol "WLTW"'),
    ("2018-05-31-Evergy-Set-to-Join-S-P-500-Navient-and-Integra-Lifesciences-Holdings-to-Join-S-P-MidCap-400-Ambac-Financial-Group-to-Join-S-P-SmallCap-600",
     "Evergy (renamed from Westar Energy)", {"symbol": "WR", "exchange": "NYSE"},
     "will be renamed Evergy and trade under the symbol EVRG"),
]

# Releases that word S&P 500 changes but change nothing in it (read and checked).
NO_SP500_CHANGE: dict[str, str] = {
    "standard--poors-announces-changes-to-us-indices-117829473.html": "S&P 100 changes only; all stay in the S&P 500",
    "standard--poors-announces-change-to-us-index-128346593.html": "SmallCap 600 change; acquirer is an S&P 500 member",
    "2015-01-21-S-P-U-S-Indices-Methodology-Update": "share-class method announced; the lines were added per 2015-08-10",
    "2016-03-11-Danaher-Duke-Energy-and-NextEra-Energy-Set-to-Join-the-S-P-100": "S&P 100 changes only",
    "New-Fox-Continues-in-S-P-500": "\"new\" Fox to continue in the S&P 500; the change came on 2019-03-14",
    "Introduces-S-P-500-Twitter-Sentiment-Index": "new index launch",
    "2022-03-04-Charles-Schwab-Set-to-Join-S-P-100-BellRing-Brands-to-Join-S-P-MidCap-400-Cerence-to-Join-S-P-SmallCap-600": "S&P 100 change only",
    "2025-02-05-Millrose-Properties-Set-to-Join-S-P-SmallCap-600": "Lennar stays in the S&P 500 after the spin-off",
    "2012-03-09-S-P-Indices-Announces-Changes-to-U-S-Index": "S&P 100 changes only; all stay in the S&P 500",
}


# Name and ticker changes of S&P 500 members that S&P announced in these releases
# (membership unchanged): (URL fragment, old symbol, new symbol, old name, new name,
# date as printed or "", quote). Empty symbols are not printed in S&P's text.
RENAMES = [
    ("standard--poors-announces-changes-to-us-indices-122687578.html", "AMB", "PLD", "AMB Property Corp.",
     "ProLogis Inc.", "", "AMB Property will be renamed ProLogis Inc. and will trade under the ticker symbol PLD"),
    ("sp-indices-announces-changes-to-us-indices-130596648.html", "FO", "", "Fortune Brands Inc.", "Beam Inc.",
     "", "which is changing its name to Beam Inc."),
    ("Baxalta-to-Join-the-500-Other-Changes-to-S-P-MidCap-400-S-P-SmallCap-600", "", "",
     "MeadWestvaco / Rock-Tenn combined company", "WestRock Co", "", "will change its name to WestRock Co"),
    ("2015-06-24-Columbia-Pipeline-to-Join-the-S-P-500-Other-Changes-to-S-P-MidCap-400-S-P-SmallCap-600", "GCI",
     "TGNA", "Gannett Co. Inc. (parent)", "TEGNA Inc.", "", 'change its name to TEGNA Inc. and trade under the symbol "TGNA"'),
    ("2015-10-27-Blackrock-Set-to-Join-the-S-P-100-Hewlett-Packard-Enterprise-to-Join-the-S-P-500", "HPQ", "",
     "Hewlett-Packard Co. (stub)", "HP Inc.", "", "which will change its name to HP Inc."),
    ("2015-12-28-Willis-Group-Holdings-Set-to-Join-the-S-P-500-Fossil-Group-to-Join-S-P-MidCap-400-Adeptus-Health-to-Join-S-P-SmallCap-600",
     "WSH", "WLTW", "Willis Group Holdings plc", "Willis Towers Watson plc", "",
     'trade under the ticker symbol "WLTW"'),
    ("2016-01-13-Extra-Space-Storage-Set-to-Join-the-S-P-500", "ACE", "CB", "ACE Ltd.", "Chubb Limited", "",
     'ACE will change its name to Chubb Limited and trade under the ticker symbol "CB"'),
    ("2016-02-26-PrivateBancorp-Set-to-Join-the-S-P-MidCap-400-Cogent-Communications-to-Join-S-P-SmallCap-600",
     "XRAY", "", "Dentsply International Inc.", "Dentsply Sirona", "",
     "Dentsply International will change its name to Dentsply Sirona"),
    ("2017-08-24-Charter-Communications-Set-to-Join-S-P-100-Quintiles-IMS-Holdings-and-SBA-Communications-to-Join-S-P-500",
     "DOW", "DWDP", "The Dow Chemical Company (combined with du Pont)", "DowDuPont Inc.", "",
     'will change its name to DowDuPont Inc. and trade under the ticker "DWDP"'),
    ("2017-11-28-Delphi-Technologies-Set-to-Join-S-P-MidCap-400-and-Frontier-Communications-to-Join-S-P-SmallCap-600",
     "DLPH", "APTV", "Delphi Automotive plc", "Aptiv plc", "", "to be renamed Aptiv plc and trade under new symbol APTV"),
    ("2018-05-31-Evergy-Set-to-Join-S-P-500-Navient-and-Integra-Lifesciences-Holdings-to-Join-S-P-MidCap-400-Ambac-Financial-Group-to-Join-S-P-SmallCap-600",
     "WR", "EVRG", "Westar Energy Inc.", "Evergy", "", "will be renamed Evergy and trade under the symbol EVRG"),
    ("2019-03-14-Fox-Set-to-Join-S-P-500-Adobe-to-Join-S-P-100", "FOXA", "TFCFA",
     "Twenty-First Century Fox Inc. Class A", "Twenty-First Century Fox Inc. Class A", "March 19, 2019",
     "Twenty-First Century Fox will change its Class A common stock ticker from FOXA to TFCFA"),
    ("2019-03-14-Fox-Set-to-Join-S-P-500-Adobe-to-Join-S-P-100", "FOX", "TFCF",
     "Twenty-First Century Fox Inc. Class B", "Twenty-First Century Fox Inc. Class B", "March 19, 2019",
     "Twenty-First Century Fox will change its Class A common stock ticker from FOXA to TFCFA"),
    ("2019-03-14-Fox-Set-to-Join-S-P-500-Adobe-to-Join-S-P-100", "FOXAV", "FOXA", "Fox Corp. Class A",
     "Fox Corp. Class A", "March 19, 2019", "Fox Corp. will change its Class A common stock ticker from FOXAV to FOXA"),
    ("2019-03-14-Fox-Set-to-Join-S-P-500-Adobe-to-Join-S-P-100", "FOXBV", "FOX", "Fox Corp. Class B",
     "Fox Corp. Class B", "March 19, 2019", "Fox Corp. will change its Class A common stock ticker from FOXAV to FOXA"),
    ("2019-05-28-Corteva-Set-to-Join-S-P-500-Fluor-to-Join-S-P-MidCap-400-and-Realogy-and-Bloomin-Brands-to-Join-S-P-SmallCap-600",
     "DWDP", "DD", "DowDuPont Inc.", "DuPont de Nemours Inc.", "",
     "It will change its name to DuPont de Nemours Inc. and its ticker symbol to DD"),
    ("2019-06-03-Bemis-Set-to-Join-S-P-500-Mattel-to-Join-S-P-MidCap-400", "BMS", "AMCR", "Bemis Company Inc.",
     "Amcor plc", "", 'will trade on the New York Stock Exchange under ticker symbol "AMCR"'),
    ("2019-11-27-W-R-Berkley-Set-to-Join-S-P-500-RLI-to-Join-S-P-MidCap-400-The-St-Joe-Company-to-Join-S-P-SmallCap-600",
     "CBS", "VIAC", "CBS Corp.", "ViacomCBS Inc.", "", "CBS will change its name to ViacomCBS Inc."),
    ("2019-12-02-Old-Dominion-Freight-Line-Set-to-Join-S-P-500-Cabot-Microelectronics-to-Join-S-P-MidCap-400-Ready-Capital-and-Industrial-Logistics-Properties-Trust-to-Join-S-P-SmallCap-600",
     "BBT", "TFC", "BB&T Corp.", "Truist Financial Corp.", "", "BB&T will change its name to Truist Financial Corp."),
    ("2020-02-27-Gardner-Denver-Holdings-Set-to-Join-S-P-500-Cimarex-Energy-to-Join-S-P-MidCap-400", "IR", "TT",
     "Ingersoll-Rand plc (\"old\")", "Trane Technologies plc", "",
     'the "old" Ingersoll-Rand will change its name and ticker to Trane Technologies plc'),
    ("2020-02-27-Gardner-Denver-Holdings-Set-to-Join-S-P-500-Cimarex-Energy-to-Join-S-P-MidCap-400", "GDI", "IR",
     "Gardner Denver Holdings Inc.", "Ingersoll Rand Inc. (\"new\")", "",
     'Gardner Denver will have a name and ticker change to "new" Ingersoll Rand Inc.'),
    ("2020-03-31-Otis-Worldwide-and-Carrier-Global-Set-to-Join-S-P-500",
     "UTX", "RTX", "United Technologies Corp.", "Raytheon Technologies Corp.", "",
     "It will change its name to Raytheon Technologies Corp. and its ticker symbol to RTX"),
    ("2012-09-25-Kraft-Foods-Group-Set-to-Join", "KFT", "MDLZ", "Kraft Foods Inc. (stub)",
     "Mondelez International Inc.", "", "will change its name to Mondelez International Inc. and its ticker symbol to MDLZ"),
    ("2016-08-25-", "TYC", "JCI", "Tyco International plc", "Johnson Controls International plc", "",
     "to form a new company called Johnson Controls International plc (NYSE: JCI)"),
    ("2016-10-24-", "AA", "ARNC", "Alcoa Inc.", "Arconic Inc.", "",
     "Alcoa will have a name change to Arconic Inc., a symbol change to ARNC"),
    ("2016-11-29-Mid-America-Apartment-Communities-AmSurg-to-Join-S-P-500", "AMSG", "", "AmSurg Corp.",
     "Envision Healthcare Corp.", "", "AmSurg will change its name to Envision Healthcare Corp."),
    ("2020-04-01-", "", "HWM", "Arconic Inc.", "Howmet Aerospace Inc.", "",
     "Howmet Aerospace Inc. (NYSE: HWM -formerly Arconic Inc.)"),
    ("2023-09-28-Veralto-Set-to-Join-S-P-500-Vestis-to-Join-S-P-MidCap-400-Others-to-Join-S-P-SmallCap-600",
     "K", "", "Kellogg Co.", "Kellanova", "", "the parent Kellogg will have a name change to Kellanova"),
    ("2024-02-26-American-Homes-4-Rent-Set-to-Join-S-P-MidCap-400", "PEAK", "DOC", "Healthpeak Properties Inc.",
     "Healthpeak Properties Inc.", "", "Healthpeak Properties will have a symbol change from PEAK to DOC"),
    ("2024-03-27-GE-Vernova-and-Solventum-Set-to-Join-S-P-500-Dentsply-Sirona-to-Join-S-P-MidCap-400-Others-to-Join-S-P-SmallCap-600",
     "GE", "", "General Electric Corp.", "GE Aerospace", "", "General Electric will have a name change to GE Aerospace"),
    ("2026-06-23-Honeywell-Aerospace-Set-to-Join-S-P-500-S-P-100-Others-to-Join-S-P-MidCap-400-and-S-P-SmallCap-600",
     "HON", "", "Honeywell International Inc.", "Honeywell Technologies Inc.", "",
     "Honeywell International will be renamed Honeywell Technologies Inc."),
    ("2026-08-13-Reddit-Set-to-Join-S-P-500-and-Sun-Communities-to-Join-S-P-MidCap-400", "EQR", "VMRK",
     "Equity Residential (combined with AvalonBay)", "Vivmark Residential", "",
     "the combined company will be renamed Vivmark Residential (NYSE: VMRK)"),
]
RENAME_FIELDS = ["announced_date", "effective_date", "old_symbol", "new_symbol", "old_company", "new_company",
                 "release_url", "release_title", "note"]


def rename_rows(releases: list[Release]) -> list[dict]:
    """RENAMES as rows; every ticker must be printed in that release, else it is an error."""
    out = []
    for suffix, old, new, old_co, new_co, when, quote in RENAMES:
        hits = [r for r in releases if suffix in r.url]
        if len(hits) != 1:
            raise SystemExit(f"RENAMES: {len(hits)} releases match {suffix}")
        rel = hits[0]
        page = rel.path.read_text(encoding="utf-8", errors="replace")
        text = plain(body_html(page))
        for sym in (old, new):
            if sym and not re.search(r"(?<![A-Z])" + re.escape(sym) + r"(?![A-Z])", text):
                raise SystemExit(f"RENAMES: {sym} not printed in {rel.url}")
        eff = parse_date(when, rel.announced)[0] if when else None
        out.append({"announced_date": rel.announced.isoformat(), "effective_date": eff.isoformat() if eff else "",
                    "old_symbol": old, "new_symbol": new, "old_company": old_co, "new_company": new_co,
                    "release_url": rel.url, "release_title": rel.title,
                    "note": sentence_with(quote, page) + ("" if when else " [date not in S&P's text]")})
    return sorted(out, key=lambda r: (r["announced_date"], r["old_symbol"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh-archive", action="store_true", help="re-read the archive listings")
    ap.add_argument("--out", default=str(HERE / "data" / "sp500_changes_2010_2026.csv"))
    ap.add_argument("--offline", action="store_true", help="use cached pages only")
    a = ap.parse_args()
    OFFLINE[0] = a.offline
    releases = release_list(a.refresh_archive)
    rows = build(releases)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    log(f"wrote {len(rows)} rows to {a.out}")
    ren = rename_rows(releases)
    ren_out = Path(a.out).with_name("sp500_ticker_changes_2010_2026.csv")
    with open(ren_out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=RENAME_FIELDS)
        w.writeheader()
        w.writerows(ren)
    log(f"wrote {len(ren)} rows to {ren_out}")
    checks(rows)
