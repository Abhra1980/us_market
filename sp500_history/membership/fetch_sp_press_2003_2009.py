#!/usr/bin/env python3
"""S&P 500 constituent changes Nov 2002 - Jan 2010 from S&P's own web pages (Wayback copies).

Fills the gap between ``build_sp500_membership.py`` (S&P's 1999-2002 change lists, to
18 Nov 2002) and ``fetch_sp_press.py`` (S&P's releases, Jan 2010 on). The window is
2002-11-19 to 2010-01-04 and overlaps both on purpose.

THE SOURCES, best first (RESEARCH.md §1 "S&P's own change notices")
-----------
1. S&P's own release text, read in Wayback Machine captures of S&P's sites:
   * ``www.spglobal.com/releases/MMDDYY.html``, S&P's U.S. index releases until the
     site closed in Feb 2003 (listed on ``usnews02.html`` / ``usnews03.html``).
   * The S&P 500 portal page of ``www2.standardandpoors.com`` (2007-2009), tab "Index
     News": an archive list of every index announcement (title, date, link). Each link is
     a portal article, either a short notice in the page itself or a redirect to a PDF
     under ``/spf/pdf/index/`` (S&P gave these PDFs scrambled names such as
     ``contemporarymonorailout546.pdf``).
   * Every captured PDF under ``/spf/pdf/index/`` whose name is not plainly a report or
     a methodology (found through the CDX listing, so PDFs no captured list links to are
     read too).
2. S&P's own tables on the same S&P 500 portal page, tab "Index Changes":
   "Implemented Index Additions and Deletions (all changes effective after close of
   trading)" - one row per change, S&P 500 only from 2007 (the Jan 2007 layout mixed
   every S&P index; those rows are filtered to "S&P 500"); its oldest row is July 2002 -
   and "Implemented Index Name and Ticker Changes". The table is paginated; each capture
   shows one page as of its capture date, so all captures are stitched together.
3. Wire copies of S&P's releases (S&P's words, republished; ``status=wire_copy``):
   PR Newswire's pages "Standard & Poor's Announces Change(s) ..." for 2003-2009, found
   through the Wayback CDX listing and read in Wayback captures (PR Newswire no longer
   serves its pre-2010 pages), plus any page listed by hand in ``WIRE_COPIES``.
4. Leads only (not S&P's words): the "Historical components of the S&P 500" Wikipedia
   table. Its 2002-2010 rows that no S&P text above covers are kept as ``lead_only``.

Captures are fetched in their raw form (``/web/<ts>id_/<url>``) and cached under
``sp500_history/downloads/sp_press_2003_2009/`` (git-ignored): ``cdx/`` listings,
``portal/`` tab pages, ``article/`` portal articles, ``pdf/`` release PDFs, ``spglobal/``
old release pages, ``wire/`` and ``wiki/``. A rerun reads the cache and fetches only
what is missing; ``--offline`` never touches the network. Wayback is asked at most once
a second, with a polite back-off on 429/503 or a refused connection.

THE METHOD
----------
1. Release text is read with ``fetch_sp_press.py``'s helpers plus a wider sentence
   parser here (S&P printed "(NYSE:XYZ)", "(NYSE: XYZ)" and, by late 2009, a bare "(XYZ)";
   lists "A (X), B (Y) and C (Z) will replace D (U), E (V) and F (W) in the S&P 500" are
   paired in order). One row per ticker. "Prior to the open on D" gives D, "after the
   close on D" the next NYSE trading day (``nyse_calendar``); "removed from the S&P 500
   after today's close" gives the release date. "A date to be announced" gives
   ``status=date_tbd``.
2. A table row "S&P 500 | added co | ticker | deleted co | ticker | D" gives an include
   and an exclude effective the NYSE trading day after D ("all changes effective after
   close of trading"). The table prints no announcement date. S&P edited some rows
   between captures (the Sep 2008 captures print mid-2008 rows a trading day late; later
   captures print them as the releases do): the version in the latest capture is used
   and the others are named in the note. One garbled row (a ticker change printed in the
   add/delete columns) is left out and logged.
3. The same change seen in many captures, in a release, its wire copy and the table is
   one row pair. S&P's own release text is kept first (announcement date, exchange,
   sentence), then the table row, then a wire copy; the others are named in the note,
   and a table row takes its announcement date and exchange from the release or wire
   copy when there is one. If S&P's release and S&P's implemented-changes table give
   different dates, the table row stands and the release row is kept as ``superseded``
   with both dates in its note (S&P's own texts disagree; which is right is not settled
   here). A ``date_tbd`` release whose change is dated elsewhere is folded into the dated
   row's note.
4. Nothing is guessed: a missing ticker, exchange or date stays empty and ``note`` says
   which. ``note`` is S&P's sentence (or table row) verbatim, then remarks in [brackets].

Usage:
    python3 sp500_history/membership/fetch_sp_press_2003_2009.py            # fetch what is missing, write the CSVs
    python3 sp500_history/membership/fetch_sp_press_2003_2009.py --offline  # cached files only
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch_sp_press as P  # noqa: E402  (S&P sentence parsers)
import nyse_calendar as NC  # noqa: E402

# fetch_sp_press knows NYSE holidays from 2010 only; use the full calendar here.
P.next_trading_day = NC.next_trading_day
P.is_trading_day = NC.is_trading_day

REPO = HERE.parent.parent
CACHE = REPO / "sp500_history/downloads/sp_press_2003_2009"
UA = P.UA  # a plain browser User-Agent; no contact details are sent anywhere
WB = "http://web.archive.org"
MIN_GAP = 1.1  # seconds between requests to the Wayback Machine (at most one a second)
START, END = "2002-11-19", "2010-01-04"

_last = [0.0]
OFFLINE = [False]
log = P.log


# ---------------------------------------------------------------- fetching

def slug(s: str, n: int = 110) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", s)[:n] + "_" + hashlib.sha1(s.encode()).hexdigest()[:8]


def throttle() -> None:
    """Wait until MIN_GAP has passed since the last request of any process using this
    cache (a lock file holds the time), so parallel runs stay under one a second."""
    import fcntl
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / ".last_request", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            last = float(fh.read().strip() or 0)
        except ValueError:
            last = 0.0
        wait = MIN_GAP - (time.time() - max(last, _last[0]))
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        fh.seek(0)
        fh.truncate()
        fh.write(str(_last[0]))
        fcntl.flock(fh, fcntl.LOCK_UN)


def fetch_bytes(url: str, path: Path, refresh: bool = False, timeout: int = 90) -> bytes | None:
    """The body at url, from path when cached, else live (and cached). A 404/403 is
    remembered in '<path>.miss' so a rerun does not ask again."""
    miss = path.with_name(path.name + ".miss")
    if path.exists() and not refresh:
        return path.read_bytes()
    if miss.exists() and not refresh or OFFLINE[0]:
        return None
    for attempt in range(6):
        throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            _last[0] = time.time()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            return body
        except urllib.error.HTTPError as e:
            _last[0] = time.time()
            if e.code in (429, 502, 503, 504):
                log(f"  HTTP {e.code} ({attempt + 1}/6), backing off: {url}")
                time.sleep(20 * (attempt + 1))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            miss.write_text(str(e.code))
            return None
        except Exception as e:  # timeouts, refused connections (Wayback's rate limit), resets
            _last[0] = time.time()
            log(f"  fetch failed ({attempt + 1}/6) {url}: {e}")
            time.sleep(20 * (attempt + 1))
    return None


def cdx(name: str, params: dict, refresh: bool = False) -> list[list[str]]:
    """Wayback CDX rows (fields as asked in params['fl']), cached as cdx/<name>.txt."""
    q = urllib.parse.urlencode(params, doseq=True, safe=":/*,")
    body = fetch_bytes(f"{WB}/cdx/search/cdx?{q}", CACHE / "cdx" / f"{name}.txt", refresh, timeout=900)
    return [ln.split() for ln in (body or b"").decode("utf-8", "replace").splitlines() if ln.strip()]


def wayback(ts: str, original: str, sub: str) -> tuple[str, bytes | None]:
    """(citable Wayback URL, raw body) of one capture."""
    path = CACHE / sub / f"{ts}_{slug(re.sub(r'^https?://', '', original))}"
    return f"{WB}/web/{ts}/{original}", fetch_bytes(f"{WB}/web/{ts}id_/{original}", path)


def text_of(body: bytes | None) -> str:
    return (body or b"").decode("utf-8", "replace")


# ---------------------------------------------------------------- candidate rows

@dataclass
class Row:
    action: str                 # include | exclude
    symbol: str
    company: str
    effective: date | None
    announced: date | None
    exchange: str
    url: str
    title: str
    status: str                 # ok | date_tbd | wire_copy | lead_only | superseded
    note: str
    rank: int                   # 0 S&P release text, 1 S&P table, 2 wire copy, 3 lead
    after_close: date | None = None
    extra: list[str] = field(default_factory=list)

    def csv(self) -> dict:
        note = self.note if len(self.note) <= 400 else self.note[:397] + "..."
        if self.extra:
            note += " [" + "; ".join(self.extra) + "]"
        return {"announced_date": self.announced.isoformat() if self.announced else "",
                "effective_date": self.effective.isoformat() if self.effective else "",
                "action": self.action, "symbol": self.symbol, "exchange": self.exchange,
                "company": self.company, "release_url": self.url, "release_title": self.title,
                "status": self.status, "note": note}


def clean_cell(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return "" if re.fullmatch(r"-*|&nbsp;", s) else s


# S&P's 2002-2009 releases print "(NYSE:XYZ)", "(NYSE: XYZ)", and from late 2009 a bare
# "(XYZ)" for NYSE tickers. A bare capitalised word in brackets that is not a ticker:
NOT_TICKER = {"GICS", "REIT", "REITS", "ETF", "ADR", "ADRS", "USA", "US", "NYSE", "NASD", "NASDAQ", "AMEX",
              "EST", "EDT", "ET", "IPO", "CEO", "LLC", "LP", "PLC", "NV", "SA", "AG", "II", "III", "MLP", "TBA"}
MENTION2 = re.compile(r"\(\s*(?:(" + P.EXCH + r")\s*:\s*)?([A-Z][A-Za-z0-9.\-/]{0,7}(?:\s?wi)?)\s*\)")
TARGET_500 = re.compile(r"\s+in the (?:S&P 100 (?:and|&) )?S&P 500(?! GICS)(?:\s+[Ii]nd(?:ex|ices))?")


def mentions2(s: str) -> list[re.Match]:
    return [m for m in MENTION2.finditer(s) if m.group(2).upper().rstrip(".") not in NOT_TICKER
            and (m.group(1) or re.fullmatch(r"[A-Z][A-Z0-9.]{0,6}(?:\s?wi)?", m.group(2)))]


def name_before(s: str, start: int, floor: int) -> str:
    """The company name printed just before a ticker bracket at start."""
    head = re.sub(r"\s\((New|Old|new|old)\)", r" [\1]", s[floor:start])
    head = re.split(r"\)\s*,?\s*(?:and\s+)?|constituents?\s+|:\s|;\s|(?<=[a-z]{3})\.\s(?=[A-Z])|,\s+and\s+|"
                    r"\s+and\s+(?=[A-Z])|,\s+(?=[A-Z])|\s\*\s|^\*\s|--\s*|\s-\s|\badd\s+|\breplace\s+|"
                    r"\breplacing\s+|\bplace of\s+|\bcompany,\s+", head)[-1]
    head = head.strip()
    if len(head) > 60 and ". " in head:  # a sentence S&P ended with "Co." before the name
        head = head.rsplit(". ", 1)[-1]
    return re.sub(r"\[(New|Old|new|old)\]", r"(\1)", head).strip(" ,*-")


ABBREV = r"(?<!\bCo)(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bBros)(?<!\bSt)(?<!\bJr)(?<!\bMt)(?<!\bvs)(?<!\bNo)(?<!\bIntl)"


def sentences2(text: str) -> list[str]:
    """Sentences, not split after 'Co.', 'Inc.', 'Corp.' and the like, nor at initials."""
    return re.split(r"(?<=[a-z0-9)\]])" + ABBREV + r"(?<!\b[A-Z])\.\s+(?=[A-Z*-])", text)


def prose_events2(text: str) -> list[P.Event]:
    """S&P 500 changes in S&P's sentences, with or without the exchange in the brackets:
    'A (X), B (Y) and C (Z) will replace D (U), E (V) and F (W) in the S&P 500' pairs the
    lists in order; also '... will be added to / removed from the S&P 500' and '... will
    move to the S&P 500, replacing ...'. Date and timing are read later per sentence."""
    out = []
    for sent in sentences2(text):
        if "S&P 500" not in sent:
            continue
        floor = 0
        for m in re.finditer(r"\bwill replace\b", sent):
            tgt = TARGET_500.search(sent, m.end())
            nxt = re.search(r"\bwill replace\b|\bin the S&P\b", sent[m.end():])
            if not tgt or (nxt and m.end() + nxt.start() < tgt.start()):
                floor = m.end()
                continue
            subj_lo = max(floor, *(x.end() for x in re.finditer(r"in the S&P [\w &]+?(?:[Ii]nd(?:ex|ices))?[,;]", sent[:m.start()])), 0)
            subj = [x for x in mentions2(sent[:m.start()]) if x.start() >= subj_lo]
            obj = [x for x in mentions2(sent[:tgt.start()]) if x.start() >= m.end()]
            if subj and obj and len(subj) == len(obj):
                pairs = list(zip(subj, obj))
            elif len(obj) == 1 and len(subj) >= 1:
                pairs = [(subj[-1], obj[0])]
            elif subj and not obj:  # "A (X) will replace Name in the S&P 500" (no ticker for Name)
                name = sent[m.end():tgt.start()].strip(" ,")
                a = subj[-1]
                out.append(P.Event("include", a.group(2), name_before(sent, a.start(), subj_lo), "",
                                   P.norm_exchange(a.group(1) or ""), note=sent))
                ex, tk = ("", name) if re.fullmatch(r"[A-Z]{1,5}", name) else P.ticker_for_name(name, text)
                out.append(P.Event("exclude", tk, "" if tk == name else name, "", ex, note=sent))
                floor = tgt.end()
                continue
            else:
                floor = tgt.end()
                continue
            for a, b in pairs:
                out.append(P.Event("include", a.group(2), name_before(sent, a.start(), subj_lo), "",
                                   P.norm_exchange(a.group(1) or ""), note=sent))
                out.append(P.Event("exclude", b.group(2), name_before(sent, b.start(), m.end()), "",
                                   P.norm_exchange(b.group(1) or ""), note=sent))
            floor = tgt.end()
        for rx, act in ((r"(?:will be|was|has been|is being) added to the S&P 500(?! GICS)", "include"),
                        (r"(?:will be|was|has been|is being) (?:removed|deleted|dropped) from the S&P 500", "exclude")):
            for m in re.finditer(rx, sent):
                cands = [x for x in mentions2(sent[:m.start()]) if m.start() - x.end() < 60]
                if cands:
                    a = cands[-1]
                    out.append(P.Event(act, a.group(2), name_before(sent, a.start(), 0), "",
                                       P.norm_exchange(a.group(1) or ""), note=sent))
        for m in re.finditer(r"will (?:move|be moved) to the S&P 500,? replacing ", sent):
            seg_end = re.search(r"\.|;|\bwhich\b|\bwhile\b|\bafter the\b", sent[m.end():])
            seg = sent[m.end():m.end() + (seg_end.start() if seg_end else 200)]
            for x in mentions2(seg):
                out.append(P.Event("exclude", x.group(2), name_before(seg, x.start(), 0), "",
                                   P.norm_exchange(x.group(1) or ""), note=sent))
    seen, uniq = set(), []
    for e in out:
        k = (e.action, e.symbol, e.note)
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq


def text_rows(text: str, announced: date, url: str, title: str, rank: int = 0,
              status: str = "ok") -> list[Row]:
    """S&P 500 changes stated in release prose."""
    evs = prose_events2(text)
    sents = sentences2(text)
    out = []
    for ev in evs:
        ev.date_raw = P.prose_date(ev, text)
        for t in P.split_tickers(ev.symbol) or [""]:
            e = P.Event(ev.action, t, ev.company, ev.date_raw, ev.exchange, note=ev.note)
            if not e.symbol:
                e.flags.append("ticker not in S&P's text")
            if not e.exchange:
                e.exchange = P.exchange_for_ticker(e.symbol, text)
            e.note = P.DATELINE.sub("", e.note) if e.note else P.key_sentence(e, sents)
            st, close = status, None
            if re.search(r"date to be (?:announced|determined)|\bTBA\b", e.date_raw or ""):
                st = "date_tbd" if status == "ok" else status
                e.flags.append("S&P: effective date to be announced")
            else:
                e.timing = P.timing_of(e, text, e.note)
                d, prob = P.parse_date(e.date_raw, announced)
                tonight = r"(?:today|tonight)['\u2019]s (?:market )?close"
                if e.action == "exclude" and e.symbol and re.search(
                        re.escape(e.symbol) + r"\)[^()]{0,60}(?:removed|deleted|dropped) from the S&P 500 (?:after|as of) "
                        + tonight, e.note) or not d and re.search(r"after " + tonight, e.note):
                    d, prob, e.timing = announced, "", "close"
                    e.flags.append("S&P: after today's close, i.e. the release date")
                if prob:
                    e.flags.append(prob)
                if d and e.timing == "open":
                    e.effective = d
                elif d and e.timing == "close":
                    e.effective, close = NC.next_trading_day(d), d
                elif d:
                    e.flags.append("cannot tell open/close")
                if not e.effective:
                    e.flags.append("no effective date in S&P's text")
            if e.symbol and not e.exchange:
                e.flags.append("exchange not in S&P's text")
            if e.symbol.endswith("wi"):
                e.flags.append("when-issued ticker as printed by S&P")
            out.append(Row(e.action, e.symbol, e.company, e.effective, announced, e.exchange, url, title,
                           st, e.note, rank, close, list(e.flags)))
    return out


# ---------------------------------------------------------------- the S&P 500 portal page

PORTAL = "standardandpoors.com/portal/site/sp/en/us/page.topic/indices_500/"
ARTICLE = "standardandpoors.com/portal/site/sp/en/us/page.article/"
PDFDIR = "standardandpoors.com/spf/pdf/index/"
FL = "timestamp,original,statuscode,digest,length"


def portal_params(original: str) -> list[str] | None:
    """The 16 comma-separated view parameters of a portal URL. [9],[10] pick the tab
    (their meaning moved between site versions); [12] is the page, [13] rows per page."""
    s = urllib.parse.unquote(original.split("indices_500/", 1)[-1]).split(".html")[0]
    p = s.split(",")
    return p if len(p) == 16 and all(x.isdigit() for x in p) else None


def portal_captures(refresh: bool) -> list[list[str]]:
    """Captures of the S&P 500 page's list tabs (news, research, changes, name/ticker):
    every paginated view, plus every first page that is not filtered by date. Tabs are
    told apart later by content, as their numbers changed between site versions."""
    rows = cdx("portal_sp500", {"url": PORTAL, "matchType": "prefix", "fl": FL,
                                "filter": "statuscode:200", "limit": "100000"}, refresh)
    out, seen = [], set()
    for r in rows:
        if "/indices_500/" not in r[1]:
            continue
        p = portal_params(r[1])
        if not p or not (2 <= int(p[9]) <= 4 and p[10] in ("1", "2")):
            continue
        if r[0] < "2008" and p[:4] == ["2", "3", "2", "2"] and p[9:11] == ["4", "1"]:
            continue  # the 2007 "Research" tab (SPIVA scorecards, papers)
        paged = p[12] != "0" or p[13] != "0"
        if not paged and (p[4] != "0" or p[5] != "0"):
            continue
        if r[3] in seen:  # same bytes as a capture already listed
            continue
        seen.add(r[3])
        out.append(r)
    return sorted(out, key=lambda r: (not (portal_params(r[1])[12] != "0" or portal_params(r[1])[13] != "0"), r[0]))


def page_kind(t: str) -> str:
    if "Implemented Index Additions and Deletions" in t:
        return "adddel"
    if "Implemented Index Name and Ticker Changes" in t:
        return "nametick"
    if "page.article/" in t and re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", t):
        return "newslist"
    return "other"


ROW_RE = re.compile(r"<tr class=\"(?:even|odd)\">(.*?)</tr>", re.S | re.I)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)


def table_cells(t: str) -> list[list[str]]:
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    return [[clean_cell(P.plain(c)) for c in TD_RE.findall(tr)] for tr in ROW_RE.findall(t)]


TICKER_CELL = re.compile(r"[A-Z][A-Z0-9.]{0,6}(?:wi)?(?:\s*\((?:new|old|New|Old)\))?")


def adddel_rows(t: str) -> list[tuple[str, str, str, str, str, str]]:
    """(index, added company, added ticker, deleted company, deleted ticker, date) from
    one capture of S&P's 'Implemented Index Additions and Deletions' table. An index-name
    row (only its first cell filled) heads the data row below it."""
    out, index = [], ""
    for cells in table_cells(t):
        if len(cells) != 5:
            continue
        if cells[0] and not any(cells[1:]):
            index = cells[0]
            continue
        if re.match(r"\d{4}-\d\d-\d\d", cells[4]):
            out.append((index, *cells[:4], cells[4][:10]))
    return out


def nametick_rows(t: str) -> list[tuple[str, str, str, str, str]]:
    """(old company, old ticker, new company, new ticker, date) from S&P's 'Implemented
    Index Name and Ticker Changes' table."""
    return [(*c[:4], c[4][:10]) for c in table_cells(t)
            if len(c) == 5 and re.match(r"\d{4}-\d\d-\d\d", c[4])]


NEWS_RE = re.compile(r"page\.article/([\d,]*?)(\d{9,})\.html\s*'[^>]*>(.*?)</a>.*?"
                     r"(\d{4}-\d\d-\d\d \d\d:\d\d):\d\d", re.S)


def news_items(t: str) -> list[tuple[str, str, str]]:
    """(article id, title, 'YYYY-MM-DD HH:MM') for each item of a news archive page."""
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    return [(aid, html.unescape(re.sub(r"<[^>]+>|\s+", " ", ti)).strip(), d)
            for _, aid, ti, d in NEWS_RE.findall(t)]


# ---------------------------------------------------------------- portal articles and PDFs

# An archive item is fetched when its title may carry an S&P 500 change (a member can
# move down under a MidCap/SmallCap headline, so those are read too).
NEWS_TITLE = re.compile(r"S&P 500|S&P 100\b|U\.?S\.? Ind|MidCap|SmallCap|Composite 1500|Replace|Change|"
                        r"\([A-Z.]{1,6}\)|Rebalanc|Constituent|Join|Added|Removed|Spin|Merger|Acqui", re.I)
NOT_NEWS = re.compile(r"Returns|Dividend|Earnings|SPIVA|Case-Shiller|Home Price|Buyback|Launch|Webcast|"
                      r"GICS|Pension|Scorecard|Survey|Commodity|Hedge|Methodology Change|Option", re.I)


def is_news_title(t: str) -> bool:
    return bool(NEWS_TITLE.search(t)) and not NOT_NEWS.search(t)


def article_captures(refresh: bool) -> dict[str, list[list[str]]]:
    """Article id -> its captures (status 200 or redirect), oldest first."""
    rows = cdx("portal_articles", {"url": ARTICLE, "matchType": "prefix",
                                   "fl": "timestamp,original,statuscode,mimetype,length", "limit": "200000"}, refresh)
    out = defaultdict(list)
    for r in rows:
        m = re.search(r"(\d{9,})\.html", r[1])
        if m and r[2] in ("200", "301", "302"):
            out[m.group(1)].append(r)
    for v in out.values():
        v.sort(key=lambda r: (r[2] != "200", r[0]))
    return out


PDF_JUMP = re.compile(r"""(?<!//)\s*window\.location\.href\s*=\s*["']\s*([^"']+\.pdf)""", re.I)


def article_content(page: str) -> tuple[str, str, str]:
    """(publication date text, body text, PDF path) of one portal article."""
    m = PDF_JUMP.search(re.sub(r"<!--.*?-->", "", page, flags=re.S))
    pdf = m.group(1).strip() if m else ""
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", page, flags=re.S | re.I)
    t = P.plain(body)
    pub = re.search(r"Publication Date:\s*([A-Z][a-z]{2} \d{1,2}, \d{4})", t)
    text = ""
    if pub:
        text = t[pub.end():]
        text = re.sub(r"^\s*\d{1,2}:\d\d\s*(?:EST|EDT|ET)?\s*", "", text)
        end = re.search(r"Regulatory Affairs|Disclaimers \||Terms of Use|Copyright \(c\)", text)
        text = text[:end.start()] if end else text
    return (pub.group(1) if pub else ""), text.strip(), pdf


def pdf_text(body: bytes, path: Path) -> str:
    """Plain text of a PDF (pdftotext, reading order), on one line per paragraph."""
    txt = path.with_suffix(path.suffix + ".txt")
    if not txt.exists():
        try:
            out = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True,
                                 timeout=60).stdout.decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        txt.write_text(out, encoding="utf-8")
    t = txt.read_text(encoding="utf-8").replace("’", "'").replace("–", "-").replace("—", "-")
    t = t.replace("•", " ").replace("", " ").replace("\x0c", " ")
    return re.sub(r"\s+", " ", t).strip()


DATELINE_RE = re.compile(r"New York,?\s*(?:NY|N\.Y\.)?,?\s*\(?([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4})")


def dateline(text: str) -> date | None:
    m = DATELINE_RE.search(text[:600])
    if not m:
        return None
    s = m.group(1).replace(".", "").replace(",", "")
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.strptime(s[:3] + " " + " ".join(s.split()[1:]), "%b %d %Y").date()
    except ValueError:
        return None


# Report, methodology and marketing PDFs in /spf/pdf/index/ that are not change notices.
NOT_RELEASE_PDF = re.compile(
    r"^(?:CS|cs_|SA_|csnational)|GICS|world ?by ?num|worlbynum|WBN|spiva|factsheet|Facthseet|method|methdlgy|faq|"
    r"brochure|white_?ppr|white_?paper|Residential|GSCI|survey|webcast|webinar|Calendar|^(?:Mar|Dec|Jun|Sept)\d{2,4}|"
    r"GIR_|InsideTheIndex|total_?return|trvalues|homeprice|Case-?Shiller|Citi|canada|japan|asx|europe|_HK|hedge|"
    r"REIT|BRIC|Aristocrat|Divid|^tr[._]|Primer|paper|launch|Earnings|EPS|Pension|OPEB|Buyback|Factbook|Global|"
    r"Custom|^Index|Rules|Sales|Thought|^SP_|^SP500_|Key|^Map|MktAtt|Licens|Proforma|^S&P|Sector|style|Target|VIX|"
    r"BXM|criteria|commentary|^fb2003|Australia|Duration|Equal_Weight|EventStudy|Executive|Expansion|Float|Frontier|"
    r"Fund|^GRA_|House|IMPACT|Indexed|Changes_Affecting|CDS|^CG_|Constituent|Core|EMBD|EMDB|ESG|Enhancements|"
    r"New_Size|RepuTex|Commodity|SPXA|Shiller|Tickers|Shrinking|USIndices2001|An%20index|Analysis|^A-Z|^A[45]_|"
    r"ABN|Effect|practice|persistence|spgra|spelsi|spmidyear|freefloat|^20\d\d_|assets|Award|saudi|Siegel|"
    r"IPOX|russia|venture|MutualFd|MSCI|macromks|stategy|rydex|advisor|currency|curreny|Metro|EquityLS|SCRRep|"
    r"ShareCount|Africa|BWInnov|IndexCalculation|divArist|GSSI|Housing|barra|Learning|Challengers|Crest|"
    r"cshome|HY-final|13030|Comm_Ppr|divgrowth|mib|Gloucester|DivRecord|STARS|TSX|Quarta|pricechanges|"
    r"\.xls|\.doc|^\d{6}[A-Za-z]*\.pdf\?|MarshallDriveT|accesswire|ChartPack|Chartpack", re.I)


def release_pdf_names(refresh: bool) -> dict[str, list[str]]:
    """PDF file name -> its first status-200 capture [timestamp, original], for every
    captured PDF in /spf/pdf/index/ that may be a change notice."""
    rows = cdx("spf_pdf_index", {"url": PDFDIR, "matchType": "prefix", "fl": "timestamp,original,statuscode,mimetype,digest,length",
                                 "filter": "statuscode:200", "collapse": "urlkey", "limit": "200000"}, refresh)
    out = {}
    for r in sorted(rows):
        name = urllib.parse.unquote(r[1].split("/spf/pdf/index/", 1)[-1].split("?")[0])
        if not name.lower().endswith(".pdf") or "/" in name:
            continue
        out.setdefault(name, r[:2])
    return out


def wanted_pdf(name: str) -> bool:
    return not NOT_RELEASE_PDF.search(name)


# ---------------------------------------------------------------- source 1a: www.spglobal.com releases

SPG_RELEASE = re.compile(r"/releases/(\d{2})(\d{2})(\d{2})[A-Za-z_]*\.html$")
SPG_FOREIGN = re.compile(r"can|euro|japan|lac|asia|adr|au|asx|hedge|spci|gl100|global|commodity|price|etf|gics", re.I)


def spglobal_rows(refresh: bool) -> list[Row]:
    """S&P's U.S. index releases on www.spglobal.com dated Nov 2002 - Feb 2003."""
    rows = cdx("spglobal_releases", {"url": "spglobal.com/releases/", "matchType": "prefix",
                                     "fl": "timestamp,original,statuscode,mimetype,length",
                                     "filter": "statuscode:200", "collapse": "urlkey", "limit": "50000"}, refresh)
    out = []
    for r in rows:
        m = SPG_RELEASE.search(r[1])
        if not m or SPG_FOREIGN.search(r[1].rsplit("/", 1)[-1][6:]):
            continue
        d = date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if not date(2002, 11, 1) <= d <= date(2003, 3, 1):
            continue
        url, body = wayback(r[0], r[1], "spglobal")
        page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text_of(body), flags=re.S | re.I)
        t = P.plain(page)
        t = t.split("(GICS)", 1)[-1].split("Copyright", 1)[0].strip()
        i = max(t.find("New York, NY"), 0)
        # drop the press contacts printed above the headline
        title = re.split(r"\S+@\S+|Index Services|Quantitative Services|Communications|Public Affairs|"
                         r"For Immediate Release", t[:i])[-1].strip()
        t = f"{title} {t[i:]}"
        out += text_rows(t, dateline(t) or d, url, title)
    return out


# ---------------------------------------------------------------- sources 1b, 1c, 2: the portal

def portal_rows(refresh: bool) -> tuple[list[Row], list[dict], list[tuple[str, str, str, str]]]:
    """S&P 500 rows of the 'Implemented Index Additions and Deletions' table, rename rows
    of the 'Name and Ticker' table, and the news archive items (id, title, date, page url)."""
    adds: dict[tuple, list[tuple[str, str]]] = defaultdict(list)  # table row -> [(capture url, ts)]
    names: dict[tuple, tuple[str, str]] = {}
    news: dict[str, tuple[str, str, str, str]] = {}
    kinds = Counter()
    for r in portal_captures(refresh):
        url, body = wayback(r[0], r[1], "portal")
        if body is None:
            continue
        t = text_of(body)
        k = page_kind(t)
        kinds[k] += 1
        if k == "adddel":
            for row in adddel_rows(t):
                if row[0].strip() == "S&P 500":
                    adds[row].append((url, r[0]))
        elif k == "nametick":
            for row in nametick_rows(t):
                names.setdefault(row, (url, r[0]))
        elif k == "newslist":
            for aid, title, when in news_items(t):
                news.setdefault(aid, (aid, title, when, url))
    log(f"portal: {sum(kinds.values())} captures read {dict(kinds)}; {len(adds)} S&P 500 table rows, "
        f"{len(names)} name/ticker rows, {len(news)} news items")

    rows = []
    title = "Implemented Index Additions and Deletions (S&P 500 page, Index Changes tab)"
    for (idx, add_co, add_tk, del_co, del_tk, d), (url, ts), other in table_versions(adds):
        if not all(TICKER_CELL.fullmatch(x) for x in (add_tk, del_tk) if x):
            log(f"  table row with a non-ticker in a ticker cell, left out: {idx} | {add_co} | {add_tk} | "
                f"{del_co} | {del_tk} | {d} ({url})")
            continue
        close = date.fromisoformat(d)
        eff = NC.next_trading_day(close)
        verbatim = f"{idx} | {add_co or '------'} | {add_tk or '------'} | {del_co or '------'} | {del_tk or '------'} | {d}"
        note = f"S&P table row (all changes effective after close of trading): {verbatim}"
        for act, co, tk in (("include", add_co, add_tk), ("exclude", del_co, del_tk)):
            if not (co or tk):
                continue
            tk = re.sub(r"\s*\((?:new|old|New|Old)\)$", "", tk)  # "BK (new)" -> BK; the note keeps S&P's cell
            extra = ["announcement date not in this table", "exchange not in this table",
                     f"effective_date is the NYSE trading day after {d}", f"capture of {ts[:8]}"] + other
            if not tk:
                extra.insert(0, "ticker not in S&P's table")
            rows.append(Row(act, tk, co, eff, None, "", url, title, "ok", note, 1, close, extra))
    ren = []
    for (old_co, old_tk, new_co, new_tk, d), (url, ts) in sorted(names.items(), key=lambda kv: kv[0][4]):
        eff = NC.next_trading_day(date.fromisoformat(d))
        ren.append({"announced_date": "", "effective_date": eff.isoformat(), "old_symbol": old_tk,
                    "new_symbol": new_tk, "old_company": old_co, "new_company": new_co, "release_url": url,
                    "release_title": "Implemented Index Name and Ticker Changes (S&P 500 page, Index Changes tab)",
                    "note": f"S&P table row (all changes effective after close of trading): {old_co} | {old_tk} | "
                            f"{new_co} | {new_tk} | {d} [effective_date is the NYSE trading day after {d}; "
                            f"announcement date not in this table; capture of {ts[:8]}]"})
    return rows, ren, sorted(news.values(), key=lambda n: n[2])


def table_versions(adds: dict) -> list:
    """One version of each table row. S&P edited some rows between captures (Sep 2008
    captures print mid-2008 rows one trading day later than both earlier and later
    captures; names were respelled). Versions with the same tickers within 10 days are
    one row; the one in the latest capture wins and the others are named in the note.
    Returns [(row, (url, ts) of the latest capture showing it, remarks)]."""
    groups: list[list[tuple]] = []
    for row in sorted(adds, key=lambda r: r[5]):
        for g in groups:
            h = g[0]
            if (h[2], h[4]) == (row[2], row[4]) and (h[2] or h[4]) and \
                    abs((date.fromisoformat(h[5]) - date.fromisoformat(row[5])).days) <= 10:
                g.append(row)
                break
        else:
            groups.append([row])
    out = []
    for g in groups:
        latest = lambda r: max(ts for _, ts in adds[r])
        best = max(g, key=latest)
        url, ts = max(adds[best], key=lambda c: c[1])
        other = [f"captures {min(t for _, t in adds[r])[:8]}-{latest(r)[:8]} print " + " | ".join(r[1:])
                 for r in g if r is not best]
        out.append((best, (url, ts), other))
    return sorted(out, key=lambda x: x[0][5])


def news_rows(news: list[tuple[str, str, str, str]], refresh: bool) -> tuple[list[Row], set[str]]:
    """S&P 500 rows from the portal articles behind the news archive items (window only),
    and the PDF names read that way."""
    caps = article_captures(refresh)
    pdfs = release_pdf_names(refresh)
    out, seen_pdf, n_read = [], set(), 0
    for aid, title, when, list_url in news:
        if not (START[:7] <= when[:7] <= END[:7]) or not is_news_title(title):
            continue
        cap = next((c for c in caps.get(aid, []) if c[2] == "200"), None)
        if not cap:
            continue
        url, body = wayback(cap[0], cap[1], "article")
        if body is None:
            continue
        n_read += 1
        pub, text, pdf = article_content(text_of(body))
        announced = date.fromisoformat(when[:10])
        if pdf:
            name = urllib.parse.unquote(pdf.rsplit("/", 1)[-1])
            seen_pdf.add(name)
            hit = pdfs.get(name)
            if not hit or not wanted_pdf(name):
                continue
            purl, pbody = wayback(hit[0], hit[1], "pdf")
            if pbody is None or not pbody.startswith(b"%PDF"):
                continue
            path = CACHE / "pdf" / f"{hit[0]}_{slug(re.sub(r'^https?://', '', hit[1]))}"
            text = pdf_text(pbody, path)
            out += text_rows(text, dateline(text) or announced, purl, title)
        elif aid in HAND_ROWS:
            out += hand_rows(HAND_ROWS[aid], text, announced, url, title)
        elif text:
            out += text_rows(text, announced, url, title)
    log(f"news archive: {n_read} articles read, {len(seen_pdf)} of them PDFs")
    return out, seen_pdf


# Portal notices whose S&P 500 changes the sentence parser cannot read, read by hand.
# Keyed by article id; every row is tied to a quoted S&P sentence (the build stops if the
# notice does not contain it). close = the after-close date S&P states.
HAND_ROWS: dict[str, list[dict]] = {
    "1204851523211": [  # 3 Nov 2009, "Schering-Plough in the S&P 500 & S&P 100"
        dict(action="exclude", symbol="", company="Schering-Plough", close=date(2009, 11, 3),
             quote="Schering-Plough will be removed from the S&P 500 and S&P 100 after tonight"),
        dict(action="include", symbol="PCLN", company="Priceline.com Inc.", close=date(2009, 11, 5),
             quote="Priceline.com Inc. (PCLN) will take the vacated place of Schering-Plough in the S&P 500"),
    ],
}


def hand_rows(entries: list[dict], text: str, announced: date, url: str, title: str) -> list[Row]:
    out = []
    for e in entries:
        sent = next((x for x in sentences2(text) if e["quote"] in x), None)
        if sent is None:
            raise SystemExit(f"HAND_ROWS: quote not in S&P's text at {url}: {e['quote']!r}")
        flags = ["read by hand", f"effective_date is the NYSE trading day after {e['close']}"]
        if not e["symbol"]:
            flags.append("ticker not in S&P's text")
        flags.append("exchange not in S&P's text")
        out.append(Row(e["action"], e["symbol"], e["company"], NC.next_trading_day(e["close"]), announced, "",
                       url, title, "ok", sent.strip(), 0, e["close"], flags))
    return out


def pdf_rows(skip: set[str], refresh: bool) -> list[Row]:
    """Every other captured /spf/pdf/index/ PDF that may be a change notice."""
    out, n = [], 0
    for name, (ts, original) in sorted(release_pdf_names(refresh).items()):
        if name in skip or not wanted_pdf(name):
            continue
        url, body = wayback(ts, original, "pdf")
        if body is None or not body.startswith(b"%PDF"):
            continue
        n += 1
        text = pdf_text(body, CACHE / "pdf" / f"{ts}_{slug(re.sub(r'^https?://', '', original))}")
        ann = dateline(text)
        if not ann or not (date(2002, 9, 1) <= ann <= date(2010, 1, 31)):
            continue
        title = re.split(r"\s+New York", text, 1)[0][:150].strip()
        out += text_rows(text, ann, url, title)
    log(f"index PDFs: {n} read")
    return out


# ---------------------------------------------------------------- sources 3 and 4: wire copies, leads

# S&P's release text republished by others, found by search for changes S&P's own pages
# lack: (URL, announcement date as the copy prints it, release title). Read live (plain
# browser User-Agent) and parsed like S&P's own text, but kept as status wire_copy.
WIRE_COPIES: list[tuple[str, str, str]] = [
]


PRN_FIRST_2010 = 82297202  # the first PR Newswire release fetch_sp_press.py reads (21 Jan 2010)


def prn_rows(refresh: bool) -> list[Row]:
    """S&P's releases as PR Newswire carried them (wire copies), read in Wayback captures:
    PR Newswire no longer serves its pre-2010 pages. The CDX listing finds them by URL."""
    rows = cdx("prn_sp_releases", {"url": "prnewswire.com/news-releases/standard--poors-announces-",
                                   "matchType": "prefix", "fl": "timestamp,original,statuscode",
                                   "collapse": "urlkey", "limit": "20000"}, refresh)
    best = {}
    for r in rows:
        m = re.search(r"-(\d+)\.html", r[1])
        if m and r[2] == "200" and int(m.group(1)) < PRN_FIRST_2010 and "?" not in r[1]:
            best.setdefault(int(m.group(1)), r)
    out = []
    for _, r in sorted(best.items()):
        url, body = wayback(r[0], r[1], "prn")
        page = text_of(body)
        d = re.search(r"<meta name=['\"]date['\"] content=['\"](\d{4}-\d\d-\d\d)", page)
        if not d:
            continue
        ann = date.fromisoformat(d.group(1))
        if not date(2002, 9, 1) <= ann <= date(2010, 1, 31):
            continue
        t = P.plain(re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", page, flags=re.S | re.I))
        m = re.search(r"NEW YORK,?\s+[A-Z][a-z]{2,8}\.?\s+\d{1,2},?(?:\s+\d{4})?\s*/\s*PRNewswire", t)
        if not m:
            continue
        t = re.split(r"\bSOURCE\s+Standard|\bAbout Standard & Poor|For more information", t[m.start():])[0]
        title = re.search(r"<title>\s*(.*?)\s*</title>", page, re.S | re.I)
        title = re.split(r"\s+--\s+|\s*\|\s*", html.unescape(title.group(1)).strip())[0] if title else ""
        out += text_rows(t, ann, url, title, rank=2, status="wire_copy")
    log(f"PR Newswire (Wayback): {len(best)} releases listed before {PRN_FIRST_2010}")
    return out


def wire_rows(refresh: bool) -> list[Row]:
    out = []
    for url, when, title in WIRE_COPIES:
        body = fetch_bytes(url, CACHE / "wire" / slug(url), refresh)
        if body is None:
            log(f"  wire copy not fetched: {url}")
            continue
        page = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", text_of(body), flags=re.S | re.I)
        text = P.plain(page)
        out += text_rows(text, date.fromisoformat(when), url, title, rank=2, status="wire_copy")
    return out


WIKI = "https://en.wikipedia.org/w/index.php?title=Historical_components_of_the_S%26P_500&action=raw"


def wiki_rows(refresh: bool) -> list[Row]:
    """Wikipedia's changes table, 2002-2010 rows: leads only (not S&P's words). Its date
    is kept in the note, not as effective_date."""
    body = fetch_bytes(WIKI, CACHE / "wiki" / "historical_components.wikitext", refresh)
    out = []
    for chunk in text_of(body).split("\n|-"):
        cells = [c.strip() for c in re.findall(r"^\|\|(.*)$", chunk, re.M)]
        if len(cells) < 5:
            continue
        try:
            d = datetime.strptime(re.sub(r"\s+", " ", cells[0]), "%B %d, %Y").date()
        except ValueError:
            continue
        if not date(2002, 11, 1) <= d <= date(2010, 1, 31):
            continue
        wl = lambda s: re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s).strip()
        reason = wl(cells[5]) if len(cells) > 5 else ""
        ref = re.search(r"url=\s*(\S+)", chunk)
        for act, tk, co in (("include", cells[1], cells[2]), ("exclude", cells[3], cells[4])):
            tk, co = wl(tk), wl(co)
            if not (tk or co):
                continue
            note = (f"Wikipedia 'Historical components of the S&P 500': {d:%B %d, %Y} | added {wl(cells[1])} "
                    f"{wl(cells[2])} | removed {wl(cells[3])} {wl(cells[4])} | {reason}")
            r = Row(act, tk, co, None, None, "", ref.group(1) if ref else WIKI.replace("&action=raw", ""),
                    "Wikipedia: Historical components of the S&P 500 (lead only)", "lead_only", note, 3,
                    extra=["not S&P's words; no S&P text found for this change", "Wikipedia's date is not used as effective_date"])
            r.after_close = d  # used for matching only
            out.append(r)
    return out


# ---------------------------------------------------------------- merging

def norm_sym(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"\s*wi$", "", s.strip()).upper())


# Two tickers S&P printed for one security in different texts of the same change.
SAME_SECURITY = {
    frozenset({"COMCV", "CMCSA"}),  # 13 Nov 2002 release "AT&T Comcast Corp. (NASDAQ:COMCV)"; table "Comcast Corp. CMCSA"
}


def same_security(a: Row, b: Row) -> bool:
    if a.symbol and b.symbol:
        x, y = norm_sym(a.symbol), norm_sym(b.symbol)
        if x == y or frozenset({x, y}) in SAME_SECURITY:
            return True
        # a misprinted ticker (table "AMIwi", release "AMPwi"): same name, same day
        return bool(a.effective and a.effective == b.effective and P.name_key(a.company)
                    and P.name_key(a.company) == P.name_key(b.company))
    ka, kb = P.name_key(a.company), P.name_key(b.company)
    if not ka or not kb:
        return False
    return ka.split()[0] == kb.split()[0] and difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.5


def when(r: Row) -> date | None:
    """The date a row is matched on: effective, else (TBD, lead) announcement or lead date."""
    return r.effective or r.announced or r.after_close


def same_change(a: Row, b: Row) -> bool:
    if a.action != b.action or not same_security(a, b):
        return False
    da, db = when(a), when(b)
    if not da or not db:
        return False
    if a.effective and b.effective:
        return abs((a.effective - b.effective).days) <= 75
    # a dated row and an undated one (date to be announced, or a lead)
    first = min(da, db)
    return -10 <= (max(da, db) - first).days <= 250


def describe(r: Row) -> str:
    if r.rank == 1:
        return f"S&P's implemented-changes table: after the close on {r.after_close}"
    if r.status == "date_tbd":
        return f"announced {r.announced} with a date to be announced ({r.url})"
    if r.rank == 2:
        return f"wire copy {r.url}"
    if r.rank == 3:
        return "Wikipedia lists it"
    return f"S&P release {r.announced} ({r.url})"


def merge(rows: list[Row]) -> list[Row]:
    """One row per change: the best source, the others named in its note."""
    rows = sorted(rows, key=lambda r: (r.rank, r.status == "date_tbd", when(r) or date.max))
    clusters: list[list[Row]] = []
    for r in rows:
        for c in clusters:
            if any(same_change(r, x) for x in c):
                c.append(r)
                break
        else:
            clusters.append([r])
    out = []
    for c in clusters:
        dated = [r for r in c if r.effective and r.rank <= 2]
        best = min(dated or c, key=lambda r: (r.rank, r.status == "date_tbd"))
        table = next((r for r in c if r.rank == 1), None)
        if best.rank == 0 and table and best.effective != table.effective:
            # S&P's release and its later implemented list disagree: the list stands.
            best.status = "superseded"
            best.extra.append(f"S&P's implemented-changes table gives after the close on {table.after_close} "
                              f"(effective {table.effective}) instead; S&P's own texts disagree")
            out.append(best)
            best = table
        if not best.symbol:
            alt = min((r for r in c if r.symbol and r.rank <= 2), key=lambda r: r.rank, default=None)
            if alt:
                best.symbol = alt.symbol
                best.extra.append(f"ticker {alt.symbol} from {describe(alt)}")
        src = lambda r: "S&P release" if r.rank == 0 else "wire copy of S&P's release"
        if not best.exchange:
            alt = min((r for r in c if r.exchange and r.rank in (0, 2) and norm_sym(r.symbol) == norm_sym(best.symbol)),
                      key=lambda r: r.rank, default=None)
            if alt:
                best.exchange = alt.exchange
                best.extra = [x for x in best.extra if not x.startswith("exchange not")]
                best.extra.append(f"exchange from {src(alt)} of {alt.announced}")
        if best.rank == 1 and best.announced is None:
            alt = max((r for r in c if r.announced and r.rank in (0, 2) and r.status != "superseded"),
                      key=lambda r: (r.rank == 0, r.announced), default=None)
            if alt:
                best.announced = alt.announced
                best.extra = [x for x in best.extra if not x.startswith("announcement date")]
                best.extra.append(f"announced_date from {src(alt)} {alt.url}")
        also = []
        for r in c:
            if r is best or r.status == "superseded":
                continue
            d = describe(r)
            if d not in also and not (r.rank == 0 and r.url == best.url):
                also.append(d)
        if also:
            best.extra.append("also: " + "; ".join(also[:4]) + (" ..." if len(also) > 4 else ""))
        out.append(best)
    return out


FIELDS = P.FIELDS
RENAME_FIELDS = P.RENAME_FIELDS


def in_window(r: Row) -> bool:
    d = r.effective or r.announced or r.after_close
    return bool(d) and START <= d.isoformat() <= END


def checks(rows: list[dict]) -> None:
    log("\nrows by status: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r["status"] for r in rows).items())))
    per = defaultdict(Counter)
    for r in rows:
        y = (r["effective_date"] or r["announced_date"] or "????")[:4]
        per[y][r["status"]] += 1
    for y in sorted(per):
        log(f"  {y}: " + ", ".join(f"{k} {v}" for k, v in sorted(per[y].items())))
    eff = {r["effective_date"] for r in rows if r["status"] == "ok" and r["effective_date"]}
    log(f"distinct effective dates with S&P's own text: {len(eff)}")
    yr = defaultdict(Counter)
    for r in rows:
        if r["status"] == "ok" and r["effective_date"]:
            yr[r["effective_date"][:4]][r["action"]] += 1
    for y in sorted(yr):
        inc, exc = yr[y]["include"], yr[y]["exclude"]
        log(f"  {y} ok: include {inc} exclude {exc}{'  <-- differ' if inc != exc else ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="use cached files only")
    ap.add_argument("--refresh-cdx", action="store_true", help="re-read the Wayback CDX listings")
    ap.add_argument("--out", default=str(HERE / "data" / "sp500_changes_2003_2009.csv"))
    a = ap.parse_args()
    OFFLINE[0] = a.offline
    rf = a.refresh_cdx

    rows = spglobal_rows(rf)
    table, renames, news = portal_rows(rf)
    rows += table
    nr, seen_pdf = news_rows(news, rf)
    rows += nr + pdf_rows(seen_pdf, rf) + prn_rows(rf) + wire_rows(False) + wiki_rows(False)
    merged = [r for r in merge(rows) if in_window(r)]
    out = sorted((r.csv() for r in merged),
                 key=lambda d: (d["effective_date"] or d["announced_date"], d["action"] == "include",
                                d["symbol"], d["status"]))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    log(f"wrote {len(out)} rows to {a.out}")
    ren = [r for r in renames if START <= r["effective_date"] <= END] + RENAMES_BY_HAND
    ren.sort(key=lambda r: (r["effective_date"] or r["announced_date"], r["old_symbol"]))
    ren_out = Path(a.out).with_name("sp500_ticker_changes_2003_2009.csv")
    with open(ren_out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=RENAME_FIELDS)
        w.writeheader()
        w.writerows(ren)
    log(f"wrote {len(ren)} rows to {ren_out}")
    checks(out)


# Name/ticker changes of S&P 500 members read in S&P's release text (not in the table).
RENAMES_BY_HAND: list[dict] = []


if __name__ == "__main__":
    main()
