#!/usr/bin/env python3
"""Complete S&P 500 index-fund holdings lists filed with the SEC, for a configurable range of period-ends.

The default range is Sep 2002 to Mar 2010 (``--from 2002-09-30 --to 2010-03-31``): the checkpoints
RESEARCH.md §1 proposes for rebuilding S&P 500 membership in 2003-2009, the years S&P's own change
notices do not cover (decision 1: a fund's list, not S&P's own file). ``--from 2010-04-30 --to 2019-09-30``
gives the lists that check the 2010-2019 membership (NPORT-P filings cover Sep 2019 onward). Nothing here
touches the database.

THE SOURCES (www.sec.gov / data.sec.gov only, fetched with a declared User-Agent)
-----------
Shareholder reports and quarterly schedules of six S&P 500 funds, listed from EDGAR's submissions JSON
(``data.sec.gov/submissions/CIK##########.json`` and its older ``files`` pages), each filing's documents
from its ``index.json``:

  | Key   | Fund (registrant CIK)                                   | Forms              | Period-ends  |
  |-------|---------------------------------------------------------|--------------------|--------------|
  | VFINX | Vanguard 500 Index Fund (Vanguard Index Funds, 36405)   | N-30D, N-CSR(S), N-Q | Mar Jun Sep Dec |
  | FUSEX | Fidelity Spartan U.S. Equity Index (Concord St, 819118) | N-30D, N-CSR(S), N-Q | Feb May Aug Nov |
  | SWPPX | Schwab S&P 500 Index Fund (Schwab Capital Trust, 904333)| N-30D, N-CSR(S), N-Q | Jan Apr Jul Oct |
  | SPY   | SPDR Trust Series 1 (884394)                            | N-30D, N-CSR       | Mar Sep        |
  | IVV   | iShares S&P 500 Index Fund (iShares Trust, 1100663)     | N-30D, N-CSR(S), N-Q | Mar Jun Sep Dec |
  | VINIX | Vanguard Institutional Index Fund (862084), cross-check | N-30D, N-CSR(S), N-Q | Mar Jun Sep Dec |

Later names: Fidelity Spartan 500 Index Fund, then Fidelity 500 Index Fund (same trust, 819118, still a
February year-end); SPDR S&P 500 ETF Trust; iShares Core S&P 500 ETF (from 2012). N-Q filings stop
with periods in early 2019 (Form N-PORT replaced them), so the last periods of 2019 may have no list
here; Vanguard's and SPY's annual and semiannual reports continue. A report date EDGAR has wrong is
corrected in REPORT_DATE_FIX after reading the filing.

Only filings whose report date is a period-end month of the fund are fetched (an iShares N-CSR for a
July year-end carries other funds). Text documents only: no images, certifications or codes of ethics.

THE METHOD
----------
1. Every document becomes lines: plain-text filings keep their columns; HTML becomes one line per
   table row with cells joined by " | " (inline tags dropped without a space, because some filings
   split words over <FONT> tags; superscript footnote marks dropped).
2. A schedule starts at a "Common Stocks" heading (SPY: its "COMMON STOCKS SHARES VALUE" header) and
   ends at Total Investments / Net Assets / End of Investments, or at the footnotes after the list.
   Lines after "Total Common Stocks" (or after a cash, futures, collateral ... heading) get section
   ``other:non-stock``, as do warrants and rights printed inside the stock list. Only that position
   or a warrant/right name makes a line non-stock, never other words in a company's name; a
   "Foreign Common Stock" list printed right after "Total Common Stock" (Schwab: Invesco Ltd., 2008-09)
   is part of the stock list and its total is added to the stated one.
3. A holding line is a name followed by shares and value. A name wrapped over two lines is joined
   (plain text: the second line is indented or reads as a continuation; HTML: a text-only row right
   above a holding row). Industry headings give ``section``. Subtotals, page headers and dates are
   skipped. Values are scaled to dollars when the column header says (000) or x 1,000.
4. The fund's schedule is the one under its own name (nearest fund heading above the list; (R) and TM
   marks ignored). A "Common Stock" line that is a row of a valuation table, followed by another
   fund's name and its list, does not swallow that list. Fidelity's schedules carry no reliable
   heading, so its trust's ~500-stock list is taken (Fidelity's reports print it twice); from 2017
   the trust also files Fidelity Flex 500 Index Fund, so a list headed "Flex" is skipped and the
   largest remaining ~500-stock list is taken.
5. Checks per list: 480-520 stock lines; the lines add up to the filing's own "Total Common Stocks"
   (or Schwab's holdings-by-category table, or total investments) to within rounding of each line; no
   "Miscellaneous Securities" bucket of unnamed holdings. ``complete`` is true only if all pass.
6. One row per (fund, period-end) in the summary: the complete list if any, an original before an
   amendment. Period-ends with no filing at all are listed too, complete = false.

Outputs, named by the range (<tag> = first year _ last year, a Jan-Mar last period-end counting to
the year before; ``--tag`` overrides), filings read if dated within nine months after the last period:
    sp500_history/downloads/sec/fundlists_<tag>/   raw filings (git-ignored)
    sp500_history/downloads/sec/fund_holdings_<tag>.csv   every line of each chosen list (git-ignored)
    sp500_history/membership/data/fund_lists_<tag>_summary.csv   one row per fund and period-end
e.g. fundlists_2002_2009 (default range) and fundlists_2010_2019 (--from 2010-04-30 --to 2019-09-30).

Usage:
    export SEC_USER_AGENT="Your Name you@example.com"
    python3 sp500_history/membership/fetch_sec_fundlists_2002_2009.py            # fetch what is missing, parse
    python3 sp500_history/membership/fetch_sec_fundlists_2002_2009.py --offline  # parse cached files only
    python3 sp500_history/membership/fetch_sec_fundlists_2002_2009.py --from 2010-04-30 --to 2019-09-30
"""
from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

USER_AGENT = os.environ.get("SEC_USER_AGENT", "").strip()
MIN_INTERVAL = 0.26                               # seconds between requests (< 4/s)
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "sp500_history/downloads/sec"
FIRST_PERIOD = "2002-09-30"                       # default range; --from / --to change it (configure())
LAST_PERIOD = "2010-03-31"
RANGE_TAG = "2002_2009"                                 # names the outputs and the raw-file cache
CACHE = OUT / f"fundlists_{RANGE_TAG}"
LAST_FILED = "2010-12-31"                         # filings dated after this are not read
FORMS = {"N-30D", "N-30D/A", "N-CSR", "N-CSR/A", "N-CSRS", "N-CSRS/A", "N-Q", "N-Q/A"}


@dataclass(frozen=True)
class Fund:
    key: str
    name: str
    cik: int
    match: str          # regex that names the S&P 500 fund in its own schedule heading
    months: tuple       # fiscal period-end months whose reports carry this fund
    exclude: str = r"$^"  # owner headings that look like the match but are another fund
    by_size: bool = False   # identify the schedule by its ~500 stock lines, not by a heading


FUNDS = [
    Fund("VFINX", "Vanguard 500 Index Fund", 36405, r"\b500\s+Index(\s+Fund)?\b", (3, 6, 9, 12)),
    # Fidelity's S&P 500 fund was "Spartan U.S. Equity Index Fund" in these years; its schedules carry no
    # fund-name heading, so the trust's one ~500-stock schedule is taken (the others hold 1,000-3,700).
    Fund("FUSEX", "Fidelity Spartan U.S. Equity Index Fund", 819118, r"(U\.\s?S\.\s+Equity|\b500)\s+Index",
         (2, 5, 8, 11), exclude=r"\bFlex\b", by_size=True),     # Fidelity Flex 500 Index (2017-): not this fund
    Fund("SWPPX", "Schwab S&P 500 Index Fund", 904333, r"SCHWAB\s+S&(?:amp;)?P\s+500\s+(INDEX\s+)?FUND",
         (1, 4, 7, 10), exclude=r"INSTITUTIONAL|SELECT\s*\(?R?\)?\s+S&P"),
    Fund("SPY", "SPDR Trust Series 1", 884394, r"SPDR", (3, 9)),
    Fund("IVV", "iShares S&P 500 Index Fund", 1100663, r"S&(?:amp;)?P\s+500\s+(Index\s+Fund|ETF)", (3, 6, 9, 12)),
    Fund("VINIX", "Vanguard Institutional Index Fund", 862084, r"Institutional\s+Index\s+Fund", (3, 6, 9, 12)),
]


# EDGAR report dates that are wrong, checked against the filing's own text.
REPORT_DATE_FIX: dict[str, str] = {
    "0001193125-14-428689": "2014-09-30",   # SPY annual report 'September 30, 2014'; EDGAR says 2013-09-30
}


# Findings from reading a filing by eye, added to that list's reason in the summary.
NOTES = {
    ("VFINX", "0000932471-11-003264"): "the filing leaves Salesforce.com out of the list: the Information Technology "
                                      "subtotal is $161,114,000 more than its lines, and Vanguard Institutional "
                                      "Index's list for the same date has Salesforce.com at that weight",
    ("SPY", "0001193125-19-302203"): "the filing prints United Rentals, United Technologies and UnitedHealth Group "
                                    "twice (across a page break); the repeated lines ($3,619,448,116) are exactly "
                                    "the difference",
    ("VFINX", "0000932471-05-000480"): "the filing prints one row with no name and no shares (value $24,416,000, "
                                      "after Navistar under Auto & Transportation); Vanguard Institutional "
                                      "Index's list for the same date has Dana Corp. there",
}


def month_end(y: int, m: int) -> date:
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def configure(first: str, last: str, tag: str | None = None) -> None:
    """Set the range of period-ends. Outputs and cache are named '<first year>_<last year>', where a
    last period-end in Jan-Mar counts to the year before (its reports close the previous year's cycle):
    2002-09-30..2010-03-31 -> '2002_2009', 2010-04-30..2019-09-30 -> '2010_2019'. Filings are read if
    dated after the first period-end and within nine months after the last one."""
    global FIRST_PERIOD, LAST_PERIOD, RANGE_TAG, CACHE, LAST_FILED
    d0, d1 = date.fromisoformat(first), date.fromisoformat(last)
    if d1 < d0:
        raise SystemExit(f"--to {last} is before --from {first}")
    FIRST_PERIOD, LAST_PERIOD = d0.isoformat(), d1.isoformat()
    RANGE_TAG = tag or f"{d0.year}_{d1.year if d1.month > 3 else d1.year - 1}"
    CACHE = OUT / f"fundlists_{RANGE_TAG}"
    m = d1.month + 9
    LAST_FILED = month_end(d1.year + (m - 1) // 12, (m - 1) % 12 + 1).isoformat()


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


# --------------------------------------------------------------------------- HTTP
class Sec:
    """Same request helper as fetch_sec_holdings.py, a little slower (another job may share the quota)."""

    def __init__(self, offline: bool) -> None:
        self.offline = offline
        self.last = 0.0
        self.requests = 0

    def get(self, url: str) -> bytes | None:
        if self.offline:
            return None
        if not USER_AGENT:
            raise SystemExit('Set SEC_USER_AGENT="Your Name you@example.com" (the SEC requires a contact), '
                             "or run with --offline to use cached files")
        assert re.match(r"https://(www|data)\.sec\.gov/", url), url   # UA goes to sec.gov only
        for attempt in range(6):
            wait = self.last + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            self.requests += 1
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept-Encoding": "gzip"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    body = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return body
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                log(f"HTTP {e.code} {url}; backing off")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                log(f"{e} {url}; backing off")
            time.sleep(min(60, 5 * 2 ** attempt))
        raise RuntimeError(f"gave up on {url}")

    def cached(self, rel: str, url: str, refresh: bool = False) -> bytes | None:
        path = CACHE / rel
        if path.exists() and not (refresh and not self.offline):
            return path.read_bytes()
        body = self.get(url)
        if body is None:
            return path.read_bytes() if path.exists() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(body)
        tmp.replace(path)
        return body


@dataclass
class Filing:
    fund: Fund
    form: str
    accession: str
    filed: str
    report: str
    primary: str


def list_filings(sec: Sec, fund: Fund) -> list[Filing]:
    rel = f"submissions/CIK{fund.cik:010d}.json"
    body = sec.cached(rel, f"https://data.sec.gov/submissions/CIK{fund.cik:010d}.json")
    if body is None:
        raise SystemExit(f"no submissions JSON for {fund.key} (offline and not cached?)")
    top = json.loads(body)
    pages = [top["filings"]["recent"]]
    for f in top["filings"].get("files", []):
        b = sec.cached(f"submissions/{f['name']}", f"https://data.sec.gov/submissions/{f['name']}")
        if b is not None:
            pages.append(json.loads(b))
    out = []
    for p in pages:
        for i, acc in enumerate(p["accessionNumber"]):
            form = p["form"][i]
            filed = p["filingDate"][i]
            rep = p["reportDate"][i]
            if form not in FORMS or not (FIRST_PERIOD < filed <= LAST_FILED):
                continue
            rep = REPORT_DATE_FIX.get(acc, rep)
            if rep and not (FIRST_PERIOD <= rep <= LAST_PERIOD and int(rep[5:7]) in fund.months):
                continue
            out.append(Filing(fund, form, acc, filed, rep, p["primaryDocument"][i]))
    return sorted(out, key=lambda f: (f.report, f.filed))


SKIP_DOC = re.compile(r"cert|906|302|ethic|coe\b|coe\.|code", re.I)


def fetch_docs(sec: Sec, f: Filing) -> list[Path]:
    """Download every text document of a filing (not images, certifications, codes of ethics)."""
    acc = f.accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{f.fund.cik}/{acc}"
    rel = f"{f.fund.key}/{f.accession}"
    body = sec.cached(f"{rel}/index.json", f"{base}/index.json")
    if body is None:
        return []
    paths = []
    for it in json.loads(body)["directory"]["item"]:
        name = it["name"]
        if not re.search(r"\.(htm|html|txt)$", name, re.I) or name.startswith(f.accession):
            continue
        if SKIP_DOC.search(name) and name != f.primary:
            continue
        if sec.cached(f"{rel}/{name}", f"{base}/{name}") is not None:
            paths.append(CACHE / rel / name)
    return paths



# --------------------------------------------------------------------------- text
TAG = re.compile(r"(?s)<[^>]*>")


BLOCKTAG = re.compile(r"(?i)<(?:br|p|div|li|h\d)\b[^>]*>|</(?:p|div|li|h\d)\s*>")


def _cell(s: str) -> str:
    # inline tags (font, span, b) can split a word ("M</FONT><FONT>cDo"): drop them without a space
    s = html.unescape(TAG.sub("", BLOCKTAG.sub(" ", s))).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _row(m: re.Match) -> str:
    cells = [_cell(c) for c in re.split(r"(?i)<t[dh]\b[^>]*>", m.group(0))[1:]]
    cells = [c for c in cells if c]
    return "\n" + " | ".join(cells) + "\n" if cells else "\n"


def _html_lines(t: str) -> list[str]:
    """One line per table row (cells joined by ' | '), one per paragraph elsewhere;
    <pre> blocks keep their own line breaks."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", t)
    # footnote marks are superscripts glued to names ('AES Corp. (The)<sup>1</sup>'); drop short ones
    t = re.sub(r"(?is)<sup\b[^>]*>\s*([^<]{0,8}?)\s*</sup\s*>",
               lambda m: " " if re.fullmatch(r"[\w,*†‡§#^ ]{0,8}", m.group(1)) else m.group(0), t)
    parts = re.split(r"(?is)(<pre\b[^>]*>.*?</pre\s*>)", t)
    out: list[str] = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.extend(html.unescape(TAG.sub("", p)).replace("\xa0", " ").replace("\r", "").split("\n"))
            continue
        p = re.sub(r"\s+", " ", p)
        p = re.sub(r"(?is)<tr\b.*?(?=<tr\b|</table|$)", _row, p)
        p = re.sub(r"(?i)<br\s*/?>|<p\b[^>]*>|</p\s*>|<div\b[^>]*>|</div\s*>|</h\d\s*>|</?table\b[^>]*>"
                   r"|<hr\b[^>]*>", "\n", p)
        p = html.unescape(TAG.sub("", p)).replace("\xa0", " ")
        for ln in p.split("\n"):
            ln = re.sub(r"[ \t]+", " ", ln).strip()
            if ln and ln != "|":
                out.append(ln)
    return out


def to_lines(raw: bytes) -> tuple[list[str], bool]:
    """(lines, is_html). Plain-text EDGAR documents keep their column layout."""
    t = raw.decode("latin-1")
    if re.search(r"(?i)<(td|tr|p|div|font|br)[\s>]", t[:3_000_000]):
        return _html_lines(t), True
    t = re.sub(r"(?i)</?(table|caption|s|c|fn|page)>", "", t)       # EDGAR text-table markup
    return [ln.rstrip() for ln in t.replace("\r", "").replace("\f", "").split("\n")], False


# --------------------------------------------------------------------------- schedule parsing
NUM = r"\$?\s*\(?\$?\s*\d[\d,]*(?:\.\d+)?\)?\*?"          # '0*' = less than half a unit
DASH = r"(?:--|—|–)"                      # a value printed as a dash (rounds to zero)
TRAIL = re.compile(rf"^(?P<name>.*?)(?P<nums>(?:\s+{NUM}|^{NUM})(?:\s+(?:{NUM}|{DASH}))*)\s*$")
NUMTOK = re.compile(r"\(?\$?\s*(\d[\d,]*(?:\.\d+)?)\)?|(?<![\w-])(?:--|—|–)(?![\w-])")
# where the common-stock list of a schedule starts
START = re.compile(r"^\s*(?:\*\s*)?(COMMON\s+STOCKS?|Common\s+Stocks?|EQUITY\s+SECURITIES|Equity\s+Securities)\b"
                   r"(?!.*continued)(?!.*\bINVESTMENTS\b)(?!.*\(Cost)(?!.*\|\s*\$)")
# a stock list that has no 'Common Stocks' heading (SPY): the column-header line
START_SPY = re.compile(r"^\s*COMMON STOCKS?\s+SHARES\s+VALUE", re.I)
END = re.compile(r"(?i)^\s*(?:\|\s*)?(?:TOTAL\s+INVESTMENTS|NET\s+ASSETS\b|TOTAL\s+NET\s+ASSETS|END\s+OF\s+(?:PORTFOLIO\s+)?(?:INVESTMENTS|HOLDINGS)"
                 r"|TOTAL\s+INVESTMENT\s+PORTFOLIO)")
AFTER_LIST = re.compile(r"(?i)^\s*\|?\s*(?:\(?\*\)?|\(\w\)|\d)?\s*\|?\s*(non-income[- ]producing|see accompanying|"
                        r"see notes|statement of assets|affiliated issuer|legend\b|notes to)")
TOTAL_STOCKS = re.compile(r"(?i)^\s*TOTAL\s+(COMMON\s+STOCKS?|EQUITY\s+SECURITIES)")
# Schwab prints a company incorporated abroad (Invesco Ltd., Bermuda) in a second stock list right after
# 'Total Common Stock': 'Foreign Common Stock 0.1% of net assets' ... 'Total Foreign Common Stock'
FOREIGN_START = re.compile(r"(?i)^\s*FOREIGN\s+COMMON\s+STOCKS?\b")
TOTAL_FOREIGN = re.compile(r"(?i)^\s*TOTAL\s+FOREIGN\s+COMMON\s+STOCKS?")
OTHER_HEAD = re.compile(
    r"(?i)^\s*(?:\(?\d+(?:\.\d+)?%\)?\s*)?(TEMPORARY\s+CASH|SHORT[- ]TERM|MONEY\s+MARKET|OTHER\s+INVESTMENT\s+COMPAN"
    r"|COLLATERAL|CASH\s+EQUIVALENT|REPURCHASE\s+AGREEMENT|FUTURES|PREFERRED\s+STOCK|RIGHTS\b|WARRANTS\b"
    r"|U\.?\s?S\.?\s+(TREASURY|GOVERNMENT|AGENCY)|CERTIFICATES\s+OF\s+DEPOSIT"
    r"|COMMERCIAL\s+PAPER|CASH\s+COLLATERAL|SECURITY\s+LENDING|SECURITIES\s+LENDING|AFFILIATED\s+MONEY)")
NOISE = re.compile(
    r"(?i)^(shares|market|value|\(000s?\)|\(000\)|market value|value \(note \d\)|amount|principal|face|"
    r"number of shares|security and number of shares|holdings by category|showing percentage of net assets|"
    r"(annual|semiannual|semi-annual|quarterly) report|schedule of investments|statement of net assets|"
    r"portfolio holdings|investments|\(unaudited\)|unaudited|\d{1,3}|see notes.*|see accompanying.*|"
    r"security|cost|\$|\(continued\)|continued)\W*$")
HEADERISH = re.compile(r"(?i)^(number\s+of\s+(shares|value)|mkt\.?\s+value|security(\s+and|\s+principal|\s*$)|"
                       r"principal\s+(amount|value))|\bvalue$|\b(shares|market\s+value|value\s*\(|\(000s?\)|x\s*1,000|\(note\s*\d\)|continued|"
                       r"schedule of investments|statement of net assets|report\b|unaudited|percentage of net assets)")
SCALE = re.compile(r"(?i)\(\s*\$?\s*\|?\s*000'?s?\s*\|?\s*\)|x\s*1,000|in\s+thousands|\$\s*\(000\)")
CONT_START = re.compile(r"(?i)(international\b|warrants?\b|rights?\b|inc\b|inc\.|corp\b|corp\.|co\b|co\.|company\b|cos\b|cos\.|group\b|ltd\b|ltd\.|"
                        r"holdings?\b|class\b|plc\b|&|and\b|of\b|n\.\s?v\.|s\.\s?a\.|l\.\s?p\.|\(the\)|-)")
CONNECT = re.compile(r"(?i)(,|&|-|--|\bof|\band|\bthe|\bde|\bfor|\bcorp\.?)$")


MONTH = re.compile(r"(?i)(?:as of\s+)?(january|february|march|april|may|june|july|august|september|october|"
                   r"november|december)")


DATE = re.compile(MONTH.pattern + r"\s+\d{1,2},?\s+\d{4}")


def nums_of(s: str) -> list[float]:
    out = []
    for m in NUMTOK.finditer(s):
        if m.group(1) is None:
            out.append(0.0)
            continue
        v = float(m.group(1).replace(",", ""))
        out.append(-v if m.group(0).startswith("(") and m.group(0).endswith(")") else v)
    return out


LEAD = re.compile(r"^\s*(?:\(\d{1,2}\)|[*o/=†‡§#^+@]+(?=\s|\(\d)|[*†‡§#^+@=]+|\(\w\))\s*")
TRAILMARK = re.compile(r"\s*(?:\*+|\(\s*(?:[a-z]{1,2}|\d{1,2})\s*\)|[†‡§#^@]+|\(\*\)|/\d{1,2}/|"
                       r"(?<=[.)])(?:\d{1,2}|[a-z])(?:,(?:\d{1,2}|[a-z]))*)\s*$")


def clean_name(s: str) -> str:
    s = s.replace("|", " ")
    s = re.sub(r"\s*\.{2,}\s*", " ", s)            # dot leaders
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(4):
        t = LEAD.sub("", s)
        t = TRAILMARK.sub("", t).strip()
        if t == s:
            break
        s = t
    return s.strip(" .,;:") + ("." if s.endswith(".") and not s.endswith("..") else "")


def split_line(s: str) -> tuple[str, list[float]]:
    """('name text', [numbers at the end of the line])."""
    flat = s.replace("|", "  ")
    flat = re.sub(r"\.{3,}", "  ", flat)
    # a name cell glued to the share count ('Stanley Black & Decker Inc.1,567,864 | 115,975')
    flat = re.sub(r"(?<=[A-Za-z.])(?=\d{1,3}(?:,\d{3})+\s{2,}\S)", " ", flat)
    m = TRAIL.match(flat)
    if not m:
        return flat.strip(), []
    nums = nums_of(m.group("nums"))
    if len(nums) > 2 and "|" in s:
        # a number that belongs to the name ('Phillips 66 | 5,811,152 | 308,572'): trust the table cells
        cells = [c.strip() for c in s.split("|")]
        if len(cells) >= 3 and all(re.fullmatch(rf"{NUM}|{DASH}", c) for c in cells[-2:]) \
                and re.search(r"[A-Za-z]\s+\d{2,4}$", cells[-3]):     # not a 1-digit footnote mark
            return "  ".join(cells[:-2]).strip(), nums_of("  ".join(cells[-2:]))
    return m.group("name").strip(), nums


SECTOR_WORD = re.compile(r"\b(CONSUMER|ENERGY|FINANCIALS?|HEALTH|INDUSTRIALS?|MATERIALS?|TECHNOLOGY|UTILITIES|"
                         r"TELECOMMUNICATIONS?|SERVICES|STAPLES|DISCRETIONARY|PRODUCER|DURABLES?|TRANSPORTATION|OILS?|"
                         r"PROCESSING|RETAIL(ING)?|BANKS|INSURANCE|MEDIA|SOFTWARE|SEMICONDUCTORS?|EQUIPMENT|"
                         r"PHARMACEUTICALS?|CHEMICALS?|AUTOMOBILES?|BEVERAGES?|FOOD|CAPITAL|GOODS|REAL|ESTATE)\b")


def is_heading(text: str) -> bool:
    """An industry heading: has a percentage, or is an all-capitals sector phrase. A lone capitalised
    word ('DENTSPLY') is not one: HTML schedules wrap names over table rows."""
    t = text.strip()
    if re.search(r"\d+(\.\d+)?\s*%", t) and not re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", t):
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    return len(letters) >= 4 and letters.isupper() and not re.search(r"\b(INC|CORP|CO|LTD|PLC|CLASS)\b", t) \
        and SECTOR_WORD.search(t.upper()) is not None


NON_STOCK = "other:non-stock"     # section of lines that are not common stock (cash, futures, warrants ...)


@dataclass
class Holding:
    line_no: int
    section: str
    name: str
    shares: float | None
    value: float | None
    raw: str
    in_list: bool = True        # printed inside the common-stock list (counts toward its stated total)

    def __post_init__(self) -> None:
        if self.section == NON_STOCK:
            self.in_list = False
        elif re.search(r"(?i)\b(warrants?|rights?)\b", self.name):
            self.section = NON_STOCK          # a warrant or right listed among the stocks
        elif self.shares is not None and self.shares < 0:
            self.section = NON_STOCK          # a sale, not a holding: Vanguard's when-issued CDK Global, 2014-09


@dataclass
class Block:
    doc: str
    start: int
    end: int
    owner: str            # nearest fund-name line before the schedule
    scale: int
    holdings: list
    stated_stocks: float | None
    stated_end: float | None
    oddities: list


OWNER = re.compile(r"(?i)^vanguard\b.*\bindex$|\bindex\s+fund\b|\bSPDR\b|\bS&P\s+500\s+fund\b|\bindex\s+trust\b|\bindex\s+funds?\b"
                   r"|\biShares\b.*\bETF\s*$")       # 'iSHARES® CORE S&P 500 ETF' (iShares' names from 2012)


def find_owner(lines: list[str], start: int, floor: int) -> str:
    """The nearest fund name above a schedule: a short line, or a table row's first cell."""
    for i in range(start - 1, max(floor, start - 1200) - 1, -1):
        cell = re.sub(r"\s*(?:®|™|\(R\)|\(TM\))", "", lines[i].split("|")[0]).strip()
        if 3 < len(cell) < 100 and OWNER.search(cell) and not re.search(r"(?i)\bfund'?s\b|\bthe fund\b", cell) \
                and len(split_line(DATE.sub("", lines[i]))[1]) < 2:   # not a holding row of a fund of funds
            return cell
        # iShares from 2018: 'Schedule of Investments (unaudited) ... | iShares® Core S&P 500 ETF (Percentages ...)'
        for c in lines[i].split("|")[1:]:
            c = re.sub(r"\s*\(Percentages[^)]*\)?$", "", re.sub(r"\s*(?:®|™|\(R\)|\(TM\))", "", c)).strip()
            if 3 < len(c) < 100 and re.fullmatch(r"(?i)iShares\b.*\bETF", c):
                return c
    return ""


def owner_key(s: str) -> str:
    return re.sub(r"[^a-z0-9&]+", " ", re.sub(r"®|™|\(R\)|\(TM\)", "", s.lower())).strip()


def parse_block(lines: list[str], start: int, stop: int, is_html: bool, owner: str = "") -> tuple[
        list, int, float | None, float | None, list]:
    """Read holdings from lines[start:stop]; return (holdings, end, stated stock total, stated end value, oddities)."""
    hold: list[Holding] = []
    odd: list[str] = []
    section = "Common Stocks"
    in_stocks = True
    pending: list[tuple[str, int]] = []      # (text, indent) of a name wrapped over lines
    sub_from = 0                             # first holding after the last industry subtotal
    stated_stocks = stated_end = None
    foreign = False                          # inside a 'Foreign Common Stock' list after the main one
    held_at_total = -1                       # holdings read when 'Total Common Stocks' was passed
    owner_at = -1                            # last fund-name line read
    i = start + 1
    end = stop
    while i < stop:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if END.match(s) and re.match(r"(?i)\s*\|?\s*END\s+OF", s):
            end = i
            break
        if END.match(s):
            vals = nums_of(re.sub(r"\(\s*Cost[^)]*\)|Cost[:\s]*\$?\s*[\d,]+", "", s))
            if not vals:
                nx = [ln for ln in lines[i + 1:i + 4] if nums_of(ln)]
                vals = nums_of(re.sub(r"\(\s*Cost[^)]*\)|Cost[:\s]*\$?\s*[\d,]+", "", nx[0])) if nx else []
            stated_end = vals[-1] if vals else None
            end = i
            break
        if not in_stocks and AFTER_LIST.match(s):
            end = i                                   # footnotes / financial statements follow the list
            break
        if not in_stocks and START.match(s.lstrip("| ")):
            end = i                                   # the next fund's schedule begins
            break
        if in_stocks and owner_at > start and START.match(s.lstrip("| ")) \
                and sum(h.line_no > owner_at for h in hold) <= 12:
            # another fund's name, its holdings-by-category table, then its stock list: the 'Common
            # Stock' this block started at was not a list (Schwab's Level 3 reconciliation table)
            end = owner_at
            hold = [h for h in hold if h.line_no < owner_at]
            break
        if not in_stocks and not foreign and len(hold) == held_at_total and FOREIGN_START.match(s.lstrip("| ")):
            in_stocks, foreign, section, pending = True, True, "Foreign Common Stock", []
            i += 1
            continue
        if foreign and (TOTAL_FOREIGN.match(s) or TOTAL_STOCKS.match(s)):
            in_stocks, section, pending, held_at_total = False, NON_STOCK, [], -2
            for j in range(i, min(i + 4, stop)):
                v = nums_of(re.sub(r"\(\s*Cost[^)]*\)|Cost[:\s]*\$?\s*[\d,]+", "", lines[j]))
                if v:
                    stated_stocks = (stated_stocks or 0) + v[-1]
                    break
            foreign = False
            i += 1
            continue
        if TOTAL_STOCKS.match(s):
            held_at_total = len(hold) if held_at_total == -1 else -2
            in_stocks = False
            section = NON_STOCK
            pending = []
            for j in range(i, min(i + 4, stop)):
                tot = re.sub(r"(\d,)\s+(\d{3})\b", r"\1\2", lines[j])      # IVV 2014-06: '57,750, 612,466'
                tot = re.sub(r"[—–-]\s*\(?\d+(?:\.\d+)?%\)?\s*$", "", tot)   # 'Total Common Stocks — 99.9%'
                v = nums_of(re.sub(r"\(\s*Cost[^)]*\)|Cost[:\s]*\$?\s*[\d,]+", "", tot))
                if v:
                    stated_stocks = v[-1]
                    break
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        name, nums = split_line(s)
        name_c = clean_name(name)
        if in_stocks and OTHER_HEAD.match(name) and len(nums) <= 1 \
                and not (pending and not nums and re.match(r"(?i)\s*(warrants?|rights?)\b", name)):
            # ('Raytheon Co. / Warrants Exp. / 6/16/2011 | 60,569 | 528': a wrapped name, not a heading)
            in_stocks, section, pending = False, NON_STOCK, []
            i += 1
            continue
        if not nums:
            if not re.search(r"[A-Za-z]", name_c) or NOISE.match(name_c) or HEADERISH.search(name_c) \
                    or OWNER.search(name_c):
                pending = []
                k1, k2 = owner_key(name_c), owner_key(owner)
                if OWNER.search(name_c) and not (k2 and (k1 in k2 or k2 in k1)):
                    owner_at = i                      # another fund's name (not a page header of this one)
            elif is_heading(name_c) and not (pending and CONNECT.search(pending[-1][0])):
                if in_stocks:
                    head = re.split(r"\s*[-–—:]*\s*\(?\s*\d", name_c)[0].strip(" -–—:(")
                    section = "Common Stocks" if START.match(head) else (head or section)
                pending = []
            else:
                pending = (pending + [(name, indent)])[-2:]
            i += 1
            continue
        if not name_c or re.fullmatch(r"[$\s]*", name_c):
            if len(nums) == 1 and in_stocks and re.fullmatch(r"\d{1,3}", s):
                pass                                    # a page number
            elif len(nums) == 1 and in_stocks:        # an industry subtotal: check the lines above it
                got = sum(h.value or 0 for h in hold[sub_from:])
                if abs(got - nums[0]) > max(2.0, 0.0005 * abs(nums[0])) and hold[sub_from:]:
                    odd.append(f"subtotal {nums[0]:,.0f} but lines since the last one sum to {got:,.0f} "
                               f"(after {hold[sub_from].name!r}, line {i})")
                sub_from = len(hold)
            if len(nums) >= 2 and pending:
                nm = clean_name(" ".join(p[0] for p in pending))
                hold.append(Holding(i, section, nm, nums[-2], nums[-1],
                                    " / ".join(lines[i - len(pending):i + 1]).strip()))
            pending = []
            i += 1
            continue
        if re.match(r"(?i)^total\b(?!\s+system)|^\(cost|^cost\b", name_c) or MONTH.fullmatch(name_c):
            # subtotals; a page header's date ('SEPTEMBER 30, 2003'); but 'Total System Services' is a stock
            pending = []
            i += 1
            continue
        if len(nums) == 1 and in_stocks and re.search(r"(?i)\b(miscellaneous|other)\s+(common\s+)?(stocks?|securities)\b",
                                                       name_c):
            hold.append(Holding(i, section, clean_name(re.sub(r"^\s*\d+\s*", "", name_c)), None, nums[0], s))
            pending = []
            i += 1
            continue
        if len(nums) == 1 and in_stocks and is_heading(name_c):        # 'Utilities (3.3%) | 1,685,726'
            head = re.split(r"\s*[-–—:]*\s*\(?\s*\d", name_c)[0].strip(" -–—:(")
            section = "Common Stocks" if START.match(head) else (head or section)
            pending = []
            i += 1
            continue
        if len(nums) == 1:
            if in_stocks and not SCALE.search(s) and not re.search(r"(?i)spdr|see financial notes|schedules? of inv", s):
                odd.append(f"one number: {s[:120]}")
            pending = (pending + [(name, indent)])[-2:] if not in_stocks else []
            i += 1
            continue
        if len(nums) > 2:
            # footnote numbers in parentheses before the shares, e.g. 'Corp. (1) 1,234 5,678'
            if in_stocks and not re.search(r"\(\s*\d{1,2}\s*\|?\s*\)\s*\|?\s*(\(\d{1,2}\)\s*\|?\s*)?[\d,]+\s*\|?\s*[\d,]+\s*$", s):
                odd.append(f"{len(nums)} numbers: {s[:120]}")
        # a text line right above a holding (not a heading, header or note) is the first half of a
        # wrapped name; headers, headings and notes cleared `pending` already
        cont = bool(pending)
        if cont and not (is_html or indent > pending[0][1] or CONNECT.search(pending[-1][0].strip())
                         or name_c[:1].islower() or CONT_START.match(name_c)):
            odd.append(f"joined unindented wrap: {' / '.join(p[0].strip() for p in pending)[:60]!r} + {name_c[:40]!r}")
        nm = clean_name(" ".join([p[0] for p in pending] + [name])) if cont else name_c
        rl = " / ".join(lines[i - len(pending):i + 1]).strip() if cont else s
        hold.append(Holding(i, section, nm, nums[-2], nums[-1], rl))
        pending = []
        i += 1
    return hold, end, stated_stocks, stated_end, odd


SUMMARY_LINE = re.compile(r"(?i)^[\s|\d.()%-]*%[\s|)]*(foreign\s+)?common\s*(stocks?)?\b(?!.*of\s+(net\s+assets|investments))")


def summary_total(lines: list[str], start: int) -> float | None:
    """Schwab states the stock total in a 'holdings by category' table just above the list
    (common stock, plus 'foreign common stock' from 2006)."""
    total, seen = 0.0, False
    for j in range(start - 1, max(0, start - 70), -1):
        ln = lines[j]
        if not SUMMARY_LINE.match(ln):
            continue
        nxt = lines[j + 1] if j + 1 < len(lines) else ""
        mv = re.search(r"(?i)market\s+value:?\s*\|?\s*\$?\s*([\d,]+)", nxt)
        rest = SUMMARY_LINE.sub("", ln)
        v = [float(mv.group(1).replace(",", ""))] if mv else nums_of(rest)
        if not v and j + 1 < len(lines):            # 'FOREIGN COMMON' wrapped: numbers on the same line
            v = nums_of(rest)
        if v:
            total += v[-1]
            seen = True
    return total if seen else None


def find_blocks(doc: str, lines: list[str], is_html: bool) -> list[Block]:
    starts = [i for i, ln in enumerate(lines)
              if START.match(ln.strip().lstrip("|").strip()) or START_SPY.match(ln.strip())]
    blocks: list[Block] = []
    floor = 0
    k = 0
    while k < len(starts):
        st = starts[k]
        nxt = len(lines)
        owner = find_owner(lines, st, floor)
        hold, end, ss, se, odd = parse_block(lines, st, nxt, is_html, owner)
        if ss is None:
            ss = summary_total(lines, st)
        window = " ".join(lines[max(0, st - 60):st + 8])
        scale = 1000 if SCALE.search(window) else 1
        blocks.append(Block(doc, st, end, owner, scale, hold, ss, se, odd))
        # the next schedule's fund name may sit between this list's last line and its parse end
        # (notes, then 'Vanguard 500 Index Fund / Schedule of Investments', then 'Common Stocks'); cash
        # or a holdings-by-category table read after the list does not count
        listed = [h.line_no for h in hold if h.in_list]
        floor = min(end, max(listed) + 1 if listed else st + 1)
        while k < len(starts) and (starts[k] < end or starts[k] == st):
            k += 1
    return blocks


# --------------------------------------------------------------------------- selection and checks
@dataclass
class Result:
    filing: Filing
    block: Block | None
    url: str
    stock_lines: int = 0
    stock_value: float = 0.0
    complete: bool = False
    reason: str = ""
    diff: float | None = None


def stocks_of(b: Block) -> list[Holding]:
    return [h for h in b.holdings if h.section != NON_STOCK]


def listed_as_stocks(b: Block) -> list[Holding]:
    """Every line of the common-stock list, warrants included (what the stated total covers)."""
    return [h for h in b.holdings if h.in_list]


def judge(f: Filing, b: Block | None, url: str) -> Result:
    r = Result(f, b, url)
    if b is None:
        r.reason = "no schedule for this fund found in the filing"
        return r
    st = stocks_of(b)
    r.stock_lines = sum(h.shares is not None for h in st)
    r.stock_value = sum(h.value or 0 for h in st) * b.scale
    listed = sum(h.value or 0 for h in listed_as_stocks(b)) * b.scale
    why = []
    if not 480 <= r.stock_lines <= 520:
        why.append(f"{r.stock_lines} stock lines")
    if b.stated_stocks:
        stated = b.stated_stocks * b.scale
        tol = 0.5 * len(st) * b.scale + b.scale             # each line rounded to the printed unit
        r.diff = listed - stated
        if abs(stated - listed) > tol:
            why.append(f"lines sum to {listed:,.0f} vs stated total {stated:,.0f}")
    elif b.stated_end:
        ratio = listed / (b.stated_end * b.scale)
        if not 0.95 <= ratio <= 1.02:
            why.append(f"lines sum to {ratio:.1%} of the stated total investments/net assets")
    else:
        why.append("no stated total to check the lines against")
    if r.stock_value < 1e9:
        why.append(f"stock value {r.stock_value:,.0f} is implausibly small (units?)")
    misc = [h for h in st if h.shares is None]
    if misc:
        why.append(f"{len(misc)} unnamed '{misc[0].name}' line(s) worth {sum(h.value or 0 for h in misc) * b.scale:,.0f}"
                   " (holdings not listed by name)")
    if any(h.shares is not None and h.shares <= 0 for h in st):
        why.append("non-positive share count")
    r.complete = not why
    r.reason = "; ".join(why)
    return r


def analyse_filing(f: Filing) -> tuple[list[Block], list[Block]]:
    """All schedules in the filing, and those that belong to this fund."""
    rel = CACHE / f.fund.key / f.accession
    blocks: list[Block] = []
    if not rel.exists():
        return [], []
    for path in sorted(rel.iterdir()):
        if path.suffix.lower() not in (".htm", ".html", ".txt"):
            continue
        lines, is_html = to_lines(path.read_bytes())
        blocks.extend(find_blocks(path.name, lines, is_html))
    if f.fund.by_size:
        mine = [b for b in blocks if 470 <= len(stocks_of(b)) <= 530 and not re.search(f.fund.exclude, b.owner, re.I)]
        if len({(len(stocks_of(b)), b.stated_stocks) for b in mine}) > 1:     # not just one list printed twice
            log(f"  WARNING {f.accession}: {len(mine)} schedules of ~500 stocks; the largest by value is taken")
    else:
        mine = [b for b in blocks if re.search(f.fund.match, b.owner, re.I)
                and not re.search(f.fund.exclude, b.owner, re.I)]
    return blocks, mine


def month_ends(fund: Fund) -> list[str]:
    out = []
    y, mth = int(FIRST_PERIOD[:4]), int(FIRST_PERIOD[5:7])
    while f"{y:04d}-{mth:02d}" <= LAST_PERIOD[:7]:
        if mth in fund.months:
            out.append(month_end(y, mth).isoformat())
        y, mth = y + (mth == 12), mth % 12 + 1
    return out


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.part")
    with tmp.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)
    tmp.replace(path)


def fmt(v: float | None) -> str:
    if v is None:
        return ""
    return f"{v:.0f}" if float(v).is_integer() else f"{v}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="parse cached files only, no requests")
    ap.add_argument("--fund", help="only this fund key (debugging)")
    ap.add_argument("--verbose", action="store_true", help="print every schedule found")
    ap.add_argument("--from", dest="first", default=FIRST_PERIOD, metavar="YYYY-MM-DD",
                    help=f"first period-end (default {FIRST_PERIOD})")
    ap.add_argument("--to", dest="last", default=LAST_PERIOD, metavar="YYYY-MM-DD",
                    help=f"last period-end (default {LAST_PERIOD})")
    ap.add_argument("--tag", help="name for outputs and cache instead of '<first year>_<last year>'")
    args = ap.parse_args()
    configure(args.first, args.last, args.tag)
    log(f"period-ends {FIRST_PERIOD} .. {LAST_PERIOD}, filed by {LAST_FILED}; cache {CACHE.relative_to(REPO)}")
    sec = Sec(args.offline)
    holdings_rows: list[dict] = []
    summary_rows: list[dict] = []
    for fund in FUNDS:
        if args.fund and fund.key != args.fund:
            continue
        filings = list_filings(sec, fund)
        log(f"{fund.key}: {len(filings)} filings listed")
        by_period: dict[str, list[Result]] = {}
        for f in filings:
            if not args.offline:
                fetch_docs(sec, f)
            blocks, mine = analyse_filing(f)
            acc = f.accession.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{fund.cik}/{acc}/{f.primary}"
            if args.verbose:
                for b in blocks:
                    log(f"    {f.accession} {b.doc}:{b.start}-{b.end} owner={b.owner[:60]!r} "
                        f"lines={len(stocks_of(b))} other={len(b.holdings) - len(stocks_of(b))} scale={b.scale}")
            # a fund's own name can head a neighbour's schedule too: prefer the ~500-line one
            # Fidelity's trust also holds small S&P 500 funds from 2017 (Flex 500 Index): take the largest
            best = min(mine, key=lambda b: (not 470 <= len(stocks_of(b)) <= 530,
                                            -sum(h.value or 0 for h in stocks_of(b)) * b.scale if fund.by_size
                                            else -len(stocks_of(b))), default=None)
            if best is not None:
                url = f"https://www.sec.gov/Archives/edgar/data/{fund.cik}/{acc}/{best.doc}"
            res = judge(f, best, url)
            if (fund.key, f.accession) in NOTES:
                res.reason = "; ".join(x for x in (res.reason, NOTES[(fund.key, f.accession)]) if x)
            if best is None and not blocks:
                res.reason = "no schedule of investments found in the filing"
            by_period.setdefault(f.report, []).append(res)
            log(f"  {f.form:8} {f.accession} {f.report} {'COMPLETE' if res.complete else 'incomplete':10} "
                f"{res.stock_lines:4} lines {res.stock_value / 1e9:9.2f}bn diff={res.diff} {res.reason}"
                + (f" [other funds' schedules: {len(blocks) - len(mine)}]" if not mine else ""))
            if args.verbose and best is not None:
                for o in best.oddities[:15]:
                    log(f"      ? {o}")
        for period in month_ends(fund):
            if period not in by_period:
                summary_rows.append({"fund": fund.key, "period_end": period, "form": "", "accession": "", "url": "",
                                     "stock_lines": 0, "total_value_usd": "", "complete": "false",
                                     "reason": "no filing with this period-end on EDGAR for this registrant"})
        for period in sorted(by_period):
            cands = by_period[period]
            # the fund's own complete list first; originals before amendments; then the longest list
            cands.sort(key=lambda r: (not r.complete, r.block is None, r.filing.form.endswith("/A"),
                                      abs(r.stock_lines - 500)))
            r = cands[0]
            others = [c for c in cands[1:] if c.block is not None]
            note = r.reason
            if not r.complete and len(cands) > 1 and not others:
                note = (note + "; " if note else "") + f"{len(cands)} filings with this period-end, none had the schedule"
            summary_rows.append({
                "fund": fund.key, "period_end": period, "form": r.filing.form, "accession": r.filing.accession,
                "url": r.url, "stock_lines": r.stock_lines, "total_value_usd": fmt(round(r.stock_value)),
                "complete": "true" if r.complete else "false", "reason": note})
            if r.block is None:
                continue
            for n, h in enumerate(r.block.holdings, 1):
                holdings_rows.append({
                    "fund": fund.key, "cik": fund.cik, "form": r.filing.form, "accession": r.filing.accession,
                    "filing_date": r.filing.filed, "period_end": period, "line_no": n, "section": h.section,
                    "name": h.name, "shares": fmt(h.shares),
                    "value_usd": fmt(None if h.value is None else h.value * r.block.scale), "raw_line": h.raw})
    summary_rows.sort(key=lambda r: (r["fund"], r["period_end"]))
    write_csv(OUT / f"fund_holdings_{RANGE_TAG}.csv",
              ["fund", "cik", "form", "accession", "filing_date", "period_end", "line_no", "section", "name",
               "shares", "value_usd", "raw_line"], holdings_rows)
    write_csv(HERE / f"data/fund_lists_{RANGE_TAG}_summary.csv",
              ["fund", "period_end", "form", "accession", "url", "stock_lines", "total_value_usd", "complete",
               "reason"], summary_rows)
    log(f"{len(holdings_rows)} holding rows, {len(summary_rows)} (fund, period) rows, "
        f"{sum(r['complete'] == 'true' for r in summary_rows)} complete; {sec.requests} requests to sec.gov")
    return 0


if __name__ == "__main__":
    sys.exit(main())
