#!/usr/bin/env python3
"""Full holdings of S&P 500 index funds from SEC Form NPORT-P, plus an SEC CUSIP->ticker map.

These are the fund lists RESEARCH.md §1 proposes as membership checkpoints from Sep 2019
(decision 1: a fund's list, not S&P's own file). Nothing here touches the database.

THE SOURCES (all www.sec.gov / data.sec.gov, fetched with a declared User-Agent)
-----------
* NPORT-P, the public quarterly portfolio report, one per fund series per fiscal quarter
  (the third month of each quarter). Raw XML at
  ``https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/primary_doc.xml``.
  Every holding has name, title, LEI, CUSIP, ISIN, sometimes a ticker, balance, value,
  percent of net assets, asset and issuer category and country.

  | Fund | Filer CIK | Series | Period-ends |
  |---|---|---|---|
  | SPDR S&P 500 ETF Trust (SPY) | 884394 | none (single series) | Mar Jun Sep Dec |
  | Vanguard 500 Index Fund (VFIAX/VOO) | 36405 | S000002839 | Mar Jun Sep Dec |
  | Fidelity 500 Index Fund (FXAIX) | 819118 | S000006027 | Feb May Aug Nov |
  | Schwab S&P 500 Index Fund (SWPPX) | 904333 | S000005911 | Jan Apr Jul Oct |
  | iShares Core S&P 500 ETF (IVV) | 1100663 | S000004310 | Mar Jun Sep Dec |

  Series ids come from ``https://www.sec.gov/files/company_tickers_mf.json``. Each
  series' own filings are listed by EDGAR's company browse with the series id as the
  CIK (``cgi-bin/browse-edgar?action=getcompany&CIK=S000002839&type=NPORT-P&output=atom``),
  so a multi-series trust's other funds (Vanguard ~12, iShares ~400) are never fetched.
  SPY has no series id and is listed by its CIK the same way.

* Fails-to-deliver files, ``https://www.sec.gov/files/data/fails-deliver-data/cnsfailsYYYYMM{a,b}.zip``
  (first and second half of each month), pipe-delimited
  ``SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE``. They are the SEC's
  only free file pairing CUSIPs with trading symbols over time. A security appears only
  in a half-month in which it had fails, so a pairing is seen, not guaranteed.

THE METHOD
----------
1. List each fund's NPORT-P and NPORT-P/A filings (series feed), download each XML once.
2. Check every XML's series id (or filer CIK for SPY) against the fund; a mismatch stops.
3. For each (fund, report date) keep the original NPORT-P. An NPORT-P/A replaces it only
   when the amendment carries a holdings list that differs from the original's (CUSIP,
   balance) pairs; the choice is printed.
4. Write every holding line, equity or not (futures, cash, money funds, collateral keep
   their asset_cat; the consumer filters).
5. Most funds file no CUSIP ("N/A", "000000000") for non-US-domiciled members (Accenture,
   Medtronic, Chubb ...), only the ISIN. cusip_resolved fills it (see resolve_cusips);
   the filed cusip column is left as filed.
6. From the fails files, one row per distinct (cusip, symbol) with the first and last
   settlement date seen, so a ticker change shows as two rows. Temporary XXXX/ZZZZ
   symbols around a CUSIP change are kept but flagged (placeholder = Y).
7. Self-checks: equity lines per fund per period; periods per fund and month-end
   coverage combined; the latest common quarter-end's equity CUSIP sets compared across
   funds; share of equity CUSIPs that get a symbol seen within +-60 days of the report date.

SEC fair access: User-Agent with a name and email, at most 5 requests a second here
(0.21 s apart), backoff on 429/503. Downloads are cached and never fetched twice; only the
five series feeds and the not-yet-published fails files are asked for again on a rerun.

Outputs (git-ignored, under sp500_history/downloads/sec/):
    nport/<fund>/<accession>.xml, feeds/<fund>.atom, ftd/cnsfailsYYYYMMx.zip
    nport_holdings.csv, ftd_cusip_symbol.csv, selfcheck.txt

Usage:
    python3 sp500_history/membership/fetch_sec_holdings.py            # fetch what is missing, parse
    python3 sp500_history/membership/fetch_sec_holdings.py --offline  # parse cached files only
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# The SEC wants a name and email in the User-Agent. Set it per person, never in git:
#   export SEC_USER_AGENT="Your Name you@example.com"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "").strip()
MIN_INTERVAL = 0.21                               # seconds between requests (< 5/s)
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "sp500_history/downloads/sec"
START = date(2019, 9, 1)            # NPORT-P public from the Sep 2019 quarter
FTD_START = (2009, 7)              # fails files back far enough to date 2010+ ticker changes
WINDOW = timedelta(days=60)          # ticker must be seen this close to the report date


@dataclass(frozen=True)
class Fund:
    key: str
    name: str
    cik: int
    series_id: str | None            # None: single-series filer, list by CIK


FUNDS = [
    Fund("SPY", "SPDR S&P 500 ETF Trust", 884394, None),
    Fund("VFIAX", "Vanguard 500 Index Fund", 36405, "S000002839"),
    Fund("FXAIX", "Fidelity 500 Index Fund", 819118, "S000006027"),
    Fund("SWPPX", "Schwab S&P 500 Index Fund", 904333, "S000005911"),
    Fund("IVV", "iShares Core S&P 500 ETF", 1100663, "S000004310"),
]

# Files fetched by hand before this script existed; copied into the cache layout.
LEGACY = {
    "ftd/cnsfails202606a.zip": "ftd_202606a.zip",
    "nport/SPY/000141036826089410.xml": "spy_20260630.xml",
    "nport/VFIAX/000003640526000473.xml": "vfiax_2026-06-30.xml",
}

HOLDING_COLS = ["fund", "series_id", "series_name", "report_period_end", "accession", "form",
                "filed_date", "line_no", "name", "title", "lei", "cusip", "isin", "ticker",
                "balance", "units", "val_usd", "pct_val", "asset_cat", "issuer_cat", "inv_country",
                "cusip_resolved", "cusip_source"]


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


# --------------------------------------------------------------------------- HTTP
class Sec:
    def __init__(self, offline: bool) -> None:
        self.offline = offline
        self.last = 0.0
        self.requests = 0

    def get(self, url: str) -> bytes | None:
        """GET url from sec.gov; None on 404. Throttled, polite retries."""
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
                with urllib.request.urlopen(req, timeout=120) as r:
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
        path = OUT / rel
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


# --------------------------------------------------------------------------- NPORT-P
@dataclass
class Filing:
    fund: Fund
    form: str
    accession: str          # with dashes
    filed: str


def list_filings(sec: Sec, fund: Fund) -> list[Filing]:
    who = fund.series_id or f"{fund.cik:010d}"
    out: list[Filing] = []
    start = 0
    while True:
        rel = f"feeds/{fund.key}.atom" if start == 0 else f"feeds/{fund.key}_{start}.atom"
        url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
               f"&CIK={who}&type=NPORT-P&dateb=&owner=include&start={start}&count=100&output=atom")
        body = sec.cached(rel, url, refresh=True)
        if body is None:
            raise SystemExit(f"no filing list for {fund.key} (offline and not cached?)")
        entries = re.findall(r"<entry>(.*?)</entry>", body.decode("latin-1"), re.S)
        for e in entries:
            tag = lambda t: (re.search(rf"<{t}>([^<]*)", e) or [None, ""])[1].strip()  # noqa: E731
            if tag("filing-type") in ("NPORT-P", "NPORT-P/A"):
                out.append(Filing(fund, tag("filing-type"), tag("accession-number"), tag("filing-date")))
        if len(entries) < 100:
            return out
        start += 100


def strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def txt(el: ET.Element | None, path: str) -> str:
    if el is None:
        return ""
    x = el.find(path)
    return (x.text or "").strip() if x is not None and x.text else ""


def parse_nport(xml: bytes) -> tuple[dict, list[dict]]:
    root = strip_ns(ET.fromstring(xml))
    gen = root.find("formData/genInfo")
    head = {
        "series_id": txt(gen, "seriesId") or txt(root, "headerData/filerInfo/seriesClassInfo/seriesId"),
        "series_name": txt(gen, "seriesName"),
        "report_period_end": txt(gen, "repPdDate"),
        "fiscal_year_end": txt(gen, "repPdEnd"),
        "reg_cik": txt(gen, "regCik").lstrip("0"),
        "net_assets": txt(root, "formData/fundInfo/netAssets"),
    }
    rows = []
    for i, s in enumerate(root.iterfind("formData/invstOrSecs/invstOrSec"), 1):
        ids = s.find("identifiers")
        isin = tick = ""
        if ids is not None:
            for c in ids:
                if c.tag == "isin":
                    isin = c.get("value", "")
                elif c.tag == "ticker":
                    tick = c.get("value", "")
        ac = txt(s, "assetCat")
        if not ac and s.find("assetConditional") is not None:
            a = s.find("assetConditional")
            ac = f"{a.get('assetCat', '')}:{a.get('desc', '')}"
        ic = txt(s, "issuerCat")
        if not ic and s.find("issuerConditional") is not None:
            a = s.find("issuerConditional")
            ic = f"{a.get('issuerCat', '')}:{a.get('desc', '')}"
        rows.append({
            "line_no": i, "name": txt(s, "name"), "title": txt(s, "title"), "lei": txt(s, "lei"),
            "cusip": txt(s, "cusip"), "isin": isin, "ticker": tick, "balance": txt(s, "balance"),
            "units": txt(s, "units"), "val_usd": txt(s, "valUSD"), "pct_val": txt(s, "pctVal"),
            "asset_cat": ac, "issuer_cat": ic, "inv_country": txt(s, "invCountry"),
        })
    return head, rows


def holdings_key(rows: list[dict]) -> set[tuple[str, str]]:
    return {(r["cusip"], r["balance"]) for r in rows}


def fetch_nport(sec: Sec) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    for rel, old in LEGACY.items():
        if (OUT / old).exists() and not (OUT / rel).exists():
            (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT / old, OUT / rel)
    out_rows: list[dict] = []
    for fund in FUNDS:
        filings = list_filings(sec, fund)
        log(f"{fund.key}: {len(filings)} NPORT-P(/A) filings listed")
        by_period: dict[str, list[tuple[Filing, dict, list[dict]]]] = defaultdict(list)
        for f in filings:
            acc = f.accession.replace("-", "")
            xml = sec.cached(f"nport/{fund.key}/{acc}.xml",
                             f"https://www.sec.gov/Archives/edgar/data/{fund.cik}/{acc}/primary_doc.xml")
            if xml is None:
                notes.append(f"{fund.key} {f.accession}: primary_doc.xml not found")
                continue
            head, rows = parse_nport(xml)
            ok = (head["series_id"] == fund.series_id) if fund.series_id else (head["reg_cik"] == str(fund.cik))
            if not ok:
                raise SystemExit(f"{fund.key} {f.accession}: series {head['series_id']} / cik "
                                 f"{head['reg_cik']} is not this fund")
            if head["report_period_end"] < START.isoformat():
                continue
            by_period[head["report_period_end"]].append((f, head, rows))
        for period, cands in sorted(by_period.items()):
            orig = [c for c in cands if c[0].form == "NPORT-P"]
            amds = sorted([c for c in cands if c[0].form == "NPORT-P/A"], key=lambda c: c[0].filed)
            chosen = sorted(orig, key=lambda c: c[0].filed)[-1] if orig else amds[-1]
            if len(orig) > 1:
                notes.append(f"{fund.key} {period}: {len(orig)} originals, kept the latest "
                             f"{chosen[0].accession}")
            for a in amds:
                if chosen is a:
                    notes.append(f"{fund.key} {period}: only an amendment {a[0].accession} exists, used it")
                    continue
                same = holdings_key(a[2]) == holdings_key(chosen[2])
                if a[2] and not same and chosen[0].form == "NPORT-P":
                    notes.append(f"{fund.key} {period}: amendment {a[0].accession} ({a[0].filed}) has "
                                 f"different holdings ({len(a[2])} vs {len(chosen[2])} lines); used the amendment")
                    chosen = a
                else:
                    notes.append(f"{fund.key} {period}: amendment {a[0].accession} ({a[0].filed}) "
                                 f"{'has the same holdings' if a[2] else 'has no holdings'}; kept "
                                 f"{chosen[0].accession}")
            f, head, rows = chosen
            for r in rows:
                out_rows.append({"fund": fund.key, "series_id": head["series_id"],
                                 "series_name": head["series_name"],
                                 "report_period_end": period, "accession": f.accession, "form": f.form,
                                 "filed_date": f.filed, **r})
    return out_rows, notes


# --------------------------------------------------------------------------- fails-to-deliver
# Around a CUSIP change the fails files carry the old CUSIP as e.g. XOMXXXX and the new as
# XOMZZZZ for a few days; those symbols are flagged and not used to name a security.
PLACEHOLDER = re.compile(r"(XXXX|ZZZZ)$")


def fetch_ftd(sec: Sec) -> tuple[list[dict], list[str]]:
    today = date.today()
    y, m = FTD_START
    missing: list[str] = []
    pairs: dict[tuple[str, str], dict] = {}
    # The SEC's page links some files under other paths/names (cnsfails201910a_0.zip,
    # files/node/add/data_distribution/... for Feb-Apr 2020); take links from it first.
    page = sec.cached("feeds/fails_deliver_page.html",
                      "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data", refresh=True)
    links = {}
    for href, ym, half in re.findall(r'href="(/files/[^"]*?cnsfails(\d{6})([ab])[^"/]*\.zip)"',
                                     (page or b"").decode("utf-8", "replace")):
        links[f"{ym}{half}"] = "https://www.sec.gov" + href
    while (y, m) <= (today.year, today.month):
        for half in "ab":
            name = f"cnsfails{y:04d}{m:02d}{half}.zip"
            url = links.get(f"{y:04d}{m:02d}{half}",
                            f"https://www.sec.gov/files/data/fails-deliver-data/{name}")
            body = sec.cached(f"ftd/{name}", url)
            if body is None:
                missing.append(name)
                continue
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                for member in z.namelist():
                    text = z.read(member).decode("latin-1")
                    for line in text.splitlines():
                        p = line.split("|")
                        if len(p) < 5 or not p[0].strip().isdigit():
                            continue          # header, trailer, blank
                        d = p[0].strip()
                        d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
                        cusip, sym = p[1].strip().upper(), p[2].strip().upper()
                        if not cusip or not sym:
                            continue
                        rec = pairs.get((cusip, sym))
                        if rec is None:
                            pairs[(cusip, sym)] = {"cusip": cusip, "symbol": sym, "description": p[4].strip(),
                                                   "first_seen": d, "last_seen": d,
                                                   "placeholder": "Y" if PLACEHOLDER.search(sym) else ""}
                        else:
                            if d < rec["first_seen"]:
                                rec["first_seen"] = d
                            if d >= rec["last_seen"]:
                                rec["last_seen"] = d
                                rec["description"] = p[4].strip()
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return sorted(pairs.values(), key=lambda r: (r["cusip"], r["first_seen"])), missing


# --------------------------------------------------------------------------- CUSIP fill
VALID_CUSIP = re.compile(r"^[0-9A-Z]{8}[0-9]$")


def good_cusip(c: str) -> bool:
    return bool(VALID_CUSIP.match(c)) and c != "000000000"


def resolve_cusips(holdings: list[dict], ftd: list[dict]) -> None:
    """Fill cusip_resolved where the fund filed none (N/A, 000000000: most funds do this
    for non-US-domiciled issuers such as Accenture or Medtronic, giving only the ISIN).

    cusip_source, first that applies:
      filed        the fund's own CUSIP
      isin_us_ca   US/CA ISIN, whose characters 3-11 are the CUSIP
      same_isin    another line in these filings with the same ISIN and a filed CUSIP
                   (Vanguard files CINS codes such as G1151C101 for Accenture)
                   at the report date nearest this one
      isin_in_ftd  ISIN characters 3-11 are a CUSIP/CINS the fails files know (BMG..., VGG...)
    The filed cusip column is never changed."""
    by_isin: dict[str, list[tuple[date, str]]] = defaultdict(list)
    for r in holdings:
        if good_cusip(r["cusip"]) and r["isin"]:
            by_isin[r["isin"]].append((date.fromisoformat(r["report_period_end"]), r["cusip"]))
    ftd_cusips = {r["cusip"] for r in ftd}
    for r in holdings:
        c, isin = r["cusip"], r["isin"]
        if good_cusip(c):
            r["cusip_resolved"], r["cusip_source"] = c, "filed"
        elif len(isin) == 12 and isin[:2] in ("US", "CA"):
            r["cusip_resolved"], r["cusip_source"] = isin[2:11], "isin_us_ca"
        elif isin in by_isin:     # the CUSIP filed nearest in time (CUSIPs change on splits)
            d = date.fromisoformat(r["report_period_end"])
            near = min(by_isin[isin], key=lambda t: (abs((t[0] - d).days), t[1]))
            r["cusip_resolved"], r["cusip_source"] = near[1], "same_isin"
        elif len(isin) == 12 and isin[2:11] in ftd_cusips:
            r["cusip_resolved"], r["cusip_source"] = isin[2:11], "isin_in_ftd"
        else:
            r["cusip_resolved"], r["cusip_source"] = "", ""


# --------------------------------------------------------------------------- checks
def is_equity(r: dict) -> bool:
    return r["asset_cat"] == "EC"


def sec_id(r: dict) -> str:
    """One key per security across funds: resolved CUSIP, else ISIN, else name."""
    return r["cusip_resolved"] or (f"ISIN:{r['isin']}" if r["isin"] else f"NAME:{r['name'].upper()}")


def selfcheck(holdings: list[dict], ftd: list[dict], nport_notes: list[str], ftd_missing: list[str]) -> str:
    L: list[str] = []
    w = L.append
    by_fp: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in holdings:
        by_fp[(r["fund"], r["report_period_end"])].append(r)
    funds = [f.key for f in FUNDS]
    periods = sorted({p for _, p in by_fp})
    names: dict[str, str] = {}
    for r in sorted(holdings, key=lambda r: r["fund"] != "SPY"):
        names.setdefault(sec_id(r), r["name"])
    eqset = {k: {sec_id(r) for r in rows if is_equity(r)} for k, rows in by_fp.items()}

    w("== NPORT-P selection notes")
    L.extend(f"  {n}" for n in nport_notes or ["(none)"])

    w("\n== Lines per fund per report date: all / equity (assetCat EC) / distinct equity securities"
      " / equity lines with no filed CUSIP / non-equity asset cats")
    for fk in funds:
        for p in periods:
            rows = by_fp.get((fk, p))
            if not rows:
                continue
            eq = [r for r in rows if is_equity(r)]
            nofiled = sum(1 for r in eq if r["cusip_source"] != "filed")
            other = Counter(r["asset_cat"] for r in rows if not is_equity(r))
            flag = "" if 500 <= len(eq) <= 506 else "   <-- outside 500-506"
            w(f"  {fk:6} {p}  {len(rows):4} / {len(eq):4} / {len(eqset[(fk, p)]):4} / {nofiled:3}  "
              f"{dict(sorted(other.items())) if other else ''}{flag}")

    w("\n== Report dates per fund (X = holdings at that month-end)")
    w("  month    " + " ".join(f"{k:>6}" for k in funds) + "   any")
    have = {(fk, p[:7]) for fk, p in by_fp}
    gaps = []
    ym, end = (int(periods[0][:4]), int(periods[0][5:7])), (int(periods[-1][:4]), int(periods[-1][5:7]))
    while ym <= end:
        mk = f"{ym[0]:04d}-{ym[1]:02d}"
        marks = ["X" if (fk, mk) in have else "." for fk in funds]
        if "X" not in marks:
            gaps.append(mk)
        w(f"  {mk}  " + " ".join(f"{c:>6}" for c in marks) + f"   {'yes' if 'X' in marks else 'NO'}")
        ym = (ym[0] + (ym[1] == 12), ym[1] % 12 + 1)
    w(f"  month-ends with no fund list: {gaps or 'none'}")
    odd = sorted({p for _, p in by_fp if (date.fromisoformat(p) + timedelta(days=1)).day != 1})
    w(f"  report dates that are not a calendar month-end: {odd or 'none'}")

    w("\n== Equity security sets compared (key: resolved CUSIP, else ISIN)")
    quarterly = [p for p in periods if sum((fk, p) in eqset for fk in funds) >= 3]
    p = quarterly[-1]
    present = [fk for fk in funds if (fk, p) in eqset]
    union = set().union(*(eqset[(fk, p)] for fk in present))
    inter = set.intersection(*(eqset[(fk, p)] for fk in present))
    w(f"  latest common quarter-end {p}: {present}; union {len(union)}, in all {len(inter)}")
    for c in sorted(union - inter, key=lambda c: names.get(c, "")):
        w(f"    {c:22} {names.get(c, '')[:40]:40} in: {[fk for fk in present if c in eqset[(fk, p)]]}")
    base = eqset[("SPY", p)] if ("SPY", p) in eqset else union
    for fk in funds:
        if fk in present:
            continue
        mine = [q for q in periods if (fk, q) in eqset]
        q = min(mine, key=lambda q: abs((date.fromisoformat(q) - date.fromisoformat(p)).days))
        s = eqset[(fk, q)]
        w(f"  {fk} {q} vs SPY {p}: only {fk} {len(s - base)}, only SPY {len(base - s)}")
        for c in sorted(s - base, key=lambda c: names.get(c, "")):
            w(f"    + {c:22} {names.get(c, '')[:40]}")
        for c in sorted(base - s, key=lambda c: names.get(c, "")):
            w(f"    - {c:22} {names.get(c, '')[:40]}")
    w("  every quarter-end with SPY, VFIAX and IVV:")
    for q in quarterly:
        pr = [fk for fk in funds if (fk, q) in eqset]
        u = set().union(*(eqset[(fk, q)] for fk in pr))
        i = set.intersection(*(eqset[(fk, q)] for fk in pr))
        extra = {fk: len(eqset[(fk, q)] - i) for fk in pr if eqset[(fk, q)] - i}
        w(f"    {q}: union {len(u)}, in all {len(i)}, extra lines by fund {extra or '-'}")

    w("\n== CUSIP -> symbol from fails-to-deliver (pair seen within +-60 days of the report date)")
    w(f"  fails files not available: {ftd_missing or 'none'}")
    spans: dict[str, list[tuple[date, date, str]]] = defaultdict(list)
    for r in ftd:
        if r["placeholder"]:
            continue
        spans[r["cusip"]].append((date.fromisoformat(r["first_seen"]), date.fromisoformat(r["last_seen"]),
                                  r["symbol"]))
    unresolved: dict[str, set[str]] = defaultdict(set)
    ambiguous: dict[str, set[str]] = defaultdict(set)
    tot_n = tot_hit = 0
    per_line = []
    for fk in funds:
        for p in periods:
            if (fk, p) not in eqset:
                continue
            d = date.fromisoformat(p)
            ids = eqset[(fk, p)]
            hit = 0
            for c in ids:
                syms = {s for a, b, s in spans.get(c, []) if a <= d + WINDOW and b >= d - WINDOW}
                if syms:
                    hit += 1
                    if len(syms) > 1:
                        ambiguous[c] |= syms
                else:
                    unresolved[c].add(f"{fk} {p}")
            tot_n += len(ids)
            tot_hit += hit
            per_line.append(f"{fk:6} {p} {100 * hit / max(1, len(ids)):5.1f}% ({len(ids) - hit} missing)")
    for i in range(0, len(per_line), 3):
        w("  " + "   ".join(per_line[i:i + 3]))
    w(f"  overall {tot_hit}/{tot_n} = {100 * tot_hit / max(1, tot_n):.2f}% of (fund, period, security)")
    w(f"\n  equity securities without a symbol in at least one period: {len(unresolved)}")
    for c in sorted(unresolved, key=lambda c: names.get(c, "")):
        ever = sorted({f"{s} {a}..{b}" for a, b, s in spans.get(c, [])})
        u = sorted(unresolved[c])
        w(f"    {c:22} {names.get(c, '')[:36]:36} {len(u):3} periods ({u[0]} .. {u[-1]}); "
          f"fails pairs ever: {ever or '-'}")
    w(f"\n  securities with two symbols inside one window (ticker change or suffix): {len(ambiguous)}")
    for c in sorted(ambiguous):
        w(f"    {c} {names.get(c, '')[:40]:40} {sorted(ambiguous[c])}")
    return "\n".join(L)



# --------------------------------------------------------------------------- main
def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(".csv.part")
    with tmp.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="use cached files only, no requests")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sec = Sec(args.offline)

    holdings, notes = fetch_nport(sec)
    ftd, missing = fetch_ftd(sec)
    write_csv(OUT / "ftd_cusip_symbol.csv", ["cusip", "symbol", "description", "first_seen", "last_seen", "placeholder"],
              ftd)
    log(f"ftd_cusip_symbol.csv: {len(ftd)} (cusip, symbol) rows; files missing: {missing}")

    resolve_cusips(holdings, ftd)
    write_csv(OUT / "nport_holdings.csv", HOLDING_COLS, holdings)
    log(f"nport_holdings.csv: {len(holdings)} rows; cusip_source "
        f"{dict(Counter(r['cusip_source'] for r in holdings if is_equity(r)))} (equity lines)")

    report = selfcheck(holdings, ftd, notes, missing)
    (OUT / "selfcheck.txt").write_text(report + "\n")
    print(report)
    log(f"{sec.requests} requests to sec.gov")
    return 0


if __name__ == "__main__":
    sys.exit(main())
