#!/usr/bin/env python3
"""SEC Official Lists of Section 13(f) Securities, 2002 Q4 - 2010 Q1, and a CUSIP -> name -> ticker lookup.

For 2003-2009 the only complete S&P 500 lists are index funds' SEC holdings schedules, which
give company names only. These tables let a later build go name -> CUSIP -> ticker at a date.
Nothing here touches the database.

THE SOURCES (www.sec.gov, fetched with a declared User-Agent)
-----------
* The quarterly "Official List of Section 13(f) Securities", linked from
  ``https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/official-list-section-13f-securities``
  as ``/divisions/investment/13f/13flistYYYYqN.pdf``. One line per security: CUSIP
  (6 + 2 + check digit), "*" if it has listed options, issuer name, issue description
  (COM, CL A, NOTE ..., CALL, PUT), status (ADDED / DELETED since the previous list).
  Option lines (CALL / PUT) carry the underlying's 6+2... with issue 90/95 and the
  underlying's check digit, so they are not real CUSIPs.
* 2004 Q1 is not on the SEC's page and its URL returns 404; the Wayback Machine has no
  copy either (checked 2026-10-12). It is missing.
* 2002 Q4 - 2003 Q4 are scans of a dot-matrix printout (Acrobat "Paper Capture"); their
  embedded OCR text is unusable. They are re-read here with tesseract (page rendered at
  300 dpi by pdftoppm, upscaled 2x, strokes thickened, blurred; word boxes from tesseract
  TSV are put in columns by the page's own header). OCR lines keep source=ocr and the CUSIP
  check digit is tested (check_digit_ok), since OCR misreads digits. Nothing is corrected.
  2004 Q2 onward are text PDFs, read with ``pdftotext -layout``.
* The SEC fails-to-deliver CUSIP <-> symbol files written by fetch_sec_holdings.py:
  ``ftd_cusip_symbol_2004_2009.csv`` (``--ftd-from 2004-01``) and ``ftd_cusip_symbol.csv``.

OUTPUTS (git-ignored, under sp500_history/downloads/sec/)
-------
13f/13flistYYYYqN.pdf, 13f/ocr/YYYYqN/pNNNN.tsv (tesseract output cache), 13f/page.html

13f_list_2002_2010.csv: every security line of every list
    quarter, cusip (9 chars, as printed), issuer_name, issue_description, status, raw_line,
    then has_options (Y = "*"), page, source (text | ocr), check_digit_ok (Y/N; option
    lines fail by construction).

cusip_name_symbol_2002_2010.csv: one row per 9-char CUSIP seen in the 13(f) lists
    (not CALL/PUT lines; OCR lines only when the check digit is valid) or in the 2004-2009
    fails data, or in the 2009+ fails data with a first sighting before 2011:
    cusip, cusip6, issue_descriptions, issuer_names, name_first_quarter, name_last_quarter,
    symbols, symbol_first_seen, symbol_last_seen, ftd_descriptions, name_sources
    Lists are " | "-separated with their own span: "ACE LTD [2002q4..2008q1]",
    "ACE [2004-03-22..2008-07-14]". A name seen only by OCR is marked "ocr". The fails
    spans of a (CUSIP, symbol) pair seen in both fails files are merged; a 2009+ span can
    run past 2010. A pair is a sighting, not proof (see fetch_sec_holdings.py).

Usage:
    python3 sp500_history/membership/fetch_sec_13f_lists.py            # fetch missing PDFs, parse
    python3 sp500_history/membership/fetch_sec_13f_lists.py --offline  # cached PDFs only (OCR cache reused)
Needs pdftotext/pdftoppm (poppler), tesseract and Pillow for the scanned quarters.
SEC fair access: SEC_USER_AGENT="Name email" (sent to sec.gov only), <= 4 requests a second.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import gzip
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

USER_AGENT = os.environ.get("SEC_USER_AGENT", "").strip()
MIN_INTERVAL = 0.25                                   # seconds between requests (<= 4/s)
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "sp500_history/downloads/sec"
CACHE = OUT / "13f"
PAGE_URL = ("https://www.sec.gov/rules-regulations/staff-guidance/"
            "division-investment-management-frequently-asked-questions/official-list-section-13f-securities")
FIRST, LAST = (2002, 4), (2010, 1)
OCR_WORKERS = max(1, min(8, (os.cpu_count() or 2) - 2))

LIST_COLS = ["quarter", "cusip", "issuer_name", "issue_description", "status", "raw_line",
             "has_options", "page", "source", "check_digit_ok"]
LOOKUP_COLS = ["cusip", "cusip6", "issue_descriptions", "issuer_names", "name_first_quarter",
               "name_last_quarter", "symbols", "symbol_first_seen", "symbol_last_seen",
               "ftd_descriptions", "name_sources"]
FTD_FILES = ["ftd_cusip_symbol_2004_2009.csv", "ftd_cusip_symbol.csv"]
FTD_MODERN_BEFORE = "2011-01-01"        # 2009+ fails pairs kept only if first seen before this


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
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
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

    def cached(self, path: Path, url: str, refresh: bool = False) -> bytes | None:
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


def quarters() -> list[str]:
    out, (y, q) = [], FIRST
    while (y, q) <= LAST:
        out.append(f"{y}q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def fetch_pdfs(sec: Sec) -> tuple[dict[str, Path], list[str]]:
    page = sec.cached(CACHE / "page.html", PAGE_URL, refresh=True)
    links = {}
    for href, yq in re.findall(r'href="(/[^"]*?13flist(\d{4}q[1-4])[^"/]*\.pdf)"',
                               (page or b"").decode("utf-8", "replace")):
        links.setdefault(yq, "https://www.sec.gov" + href)
    got, missing = {}, []
    for yq in quarters():
        url = links.get(yq, f"https://www.sec.gov/divisions/investment/13f/13flist{yq}.pdf")
        path = CACHE / f"13flist{yq}.pdf"
        if sec.cached(path, url) is None:
            missing.append(f"{yq}{'' if yq in links else ' (not linked on the SEC page)'}")
        else:
            got[yq] = path
    return got, missing


# --------------------------------------------------------------------------- CUSIP
def check_digit(c8: str) -> int:
    s = 0
    for i, ch in enumerate(c8):
        v = int(ch) if ch.isdigit() else (ord(ch) - 55 if "A" <= ch <= "Z" else {"*": 36, "@": 37, "#": 38}[ch])
        if i % 2:
            v *= 2
        s += v // 10 + v % 10
    return (10 - s % 10) % 10


def cusip_ok(c: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Z]{8}[0-9]", c)) and check_digit(c[:8]) == int(c[8])


STATUSES = ("ADDED", "DELETED")


def norm_status(s: str) -> str:
    s = s.strip().upper()
    if not s:
        return ""
    best = difflib.get_close_matches(s, STATUSES, n=1, cutoff=0.7)
    return best[0] if best else s


def is_option(desc: str) -> bool:
    """CALL / PUT line; OCR spellings such as PIJT or CALI count too."""
    d = desc.strip().upper()
    return d in ("CALL", "PUT") or (len(d) <= 5 and bool(difflib.get_close_matches(d, ["CALL", "PUT"], 1, 0.6)))


# --------------------------------------------------------------------------- text PDFs
LINE = re.compile(r"^\s*([0-9A-Z]{6}) ([0-9A-Z]{2}) ([0-9])(\s+\*)?\s+(\S.*?)\s*$")
CHUNK = re.compile(r"\S+(?: \S+)*")          # runs separated by 2+ spaces


def parse_text_pdf(yq: str, pdf: Path, notes: list[str]) -> list[dict]:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True,
                          text=True, encoding="latin-1").stdout
    rows = []
    hdr_q = set(re.findall(r"Year:\s*(\d{4})\s+Qtr:\s*(\d)", text))
    if hdr_q and hdr_q != {(yq[:4], yq[5])}:
        notes.append(f"{yq}: page headers say {sorted(hdr_q)}")
    for pno, page in enumerate(text.split("\f"), 1):
        desc_col = status_col = None
        for line in page.splitlines():
            if "ISSUER DESCRIPTION" in line:
                desc_col, status_col = line.index("ISSUER DESCRIPTION"), line.find("STATUS")
                continue
            m = LINE.match(line)
            if not m:
                continue
            start = m.start(5)
            chunks = [(start + c.start(), c.group()) for c in CHUNK.finditer(m[5])]
            name, desc, status = [], [], ""
            if chunks and chunks[-1][1] in STATUSES:
                status = chunks.pop()[1]
            # the first run is the name; later runs left of the header's ISSUER DESCRIPTION
            # (a name printed with a double space) are name too, the rest is description
            for i, (pos, tok) in enumerate(chunks):
                (name if i == 0 or (desc_col is not None and pos < desc_col - 3) else desc).append(tok)
            if desc_col is None and len(chunks) > 2:
                notes.append(f"{yq} p{pno}: no header, split by spacing: {line.strip()}")
            cusip = m[1] + m[2] + m[3]
            rows.append({"quarter": yq, "cusip": cusip, "issuer_name": " ".join(name),
                         "issue_description": " ".join(desc), "status": status, "raw_line": line.rstrip(),
                         "has_options": "Y" if m[4] else "", "page": pno, "source": "text",
                         "check_digit_ok": "Y" if cusip_ok(cusip) else "N"})
    return rows


# --------------------------------------------------------------------------- scanned PDFs (OCR)
def is_scanned(pdf: Path) -> bool:
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, encoding="latin-1").stdout
    return "Paper Capture" in info


def page_count(pdf: Path) -> int:
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, encoding="latin-1").stdout
    return int(re.search(r"Pages:\s+(\d+)", info)[1])


def ocr_page(pdf: Path, pno: int, out: Path) -> None:
    from PIL import Image, ImageFilter           # Pillow, only needed for the scanned quarters
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "p"
        subprocess.run(["pdftoppm", "-r", "300", "-gray", "-f", str(pno), "-l", str(pno), "-singlefile",
                        str(pdf), str(base)], check=True, capture_output=True)
        im = Image.open(f"{base}.pgm").convert("L")
        im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
        im = im.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(2))
        im.save(base.with_suffix(".png"))
        tsv = subprocess.run(["tesseract", str(base.with_suffix(".png")), "-", "--psm", "6", "tsv"],
                             check=True, capture_output=True, text=True).stdout
    tmp = out.with_suffix(".part")
    tmp.write_text(tsv)
    tmp.replace(out)


def ocr_quarter(yq: str, pdf: Path) -> list[Path]:
    d = CACHE / "ocr" / yq
    d.mkdir(parents=True, exist_ok=True)
    n = page_count(pdf)
    pages = [d / f"p{p:04d}.tsv" for p in range(1, n + 1)]
    todo = [(p, f) for p, f in enumerate(pages, 1) if not f.exists()]
    if todo:
        log(f"{yq}: OCR of {len(todo)} of {n} pages ({OCR_WORKERS} workers)")
        with ThreadPoolExecutor(OCR_WORKERS) as ex:
            for i, _ in enumerate(ex.map(lambda t: ocr_page(pdf, t[0], t[1]), todo), 1):
                if i % 100 == 0:
                    log(f"  {yq}: {i}/{len(todo)} pages")
    return pages


def tsv_lines(path: Path) -> list[list[tuple[int, str]]]:
    """Words per OCR line as (left x, text), lines top to bottom."""
    lines: dict[tuple[int, int, int], list[tuple[int, int, str]]] = defaultdict(list)
    with path.open() as fh:
        for r in csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r["level"] != "5" or not (r["text"] or "").strip():
                continue
            lines[(int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))].append(
                (int(r["top"]), int(r["left"]), r["text"].strip()))
    out = []
    for words in lines.values():
        words.sort(key=lambda w: w[1])
        out.append((min(w[0] for w in words), [(w[1], w[2]) for w in words]))
    return [w for _, w in sorted(out, key=lambda t: t[0])]


def header_cols(words: list[tuple[int, str]]) -> tuple[int, int, int] | None:
    """x of ISSUER NAME, ISSUER DESCRIPTION, STATUS on a header line, by fuzzy match."""
    texts = [t.upper() for _, t in words]
    if not any("CUSIP" in t or "USIP" in t for t in texts):
        return None
    issuer = [x for x, t in words if difflib.SequenceMatcher(None, t.upper(), "ISSUER").ratio() >= 0.7]
    status = [x for x, t in words if difflib.SequenceMatcher(None, t.upper(), "STATUS").ratio() >= 0.7]
    if len(issuer) < 2 or not status:
        return None
    return issuer[0], issuer[1], status[-1]


CUSIP_OCR = re.compile(r"^([0-9A-Z]{6})([0-9A-Z]{2})([0-9])$")


def parse_ocr(yq: str, pages: list[Path], notes: list[str]) -> list[dict]:
    parsed = [(pno, tsv_lines(p)) for pno, p in enumerate(pages, 1)]
    cols = {}
    for pno, lines in parsed:
        for words in lines:
            h = header_cols(words)
            if h:
                cols[pno] = h
                break
    if not cols:
        notes.append(f"{yq}: no OCR header found on any page; quarter skipped")
        return []
    med = tuple(sorted(c[i] for c in cols.values())[len(cols) // 2] for i in range(3))
    rows = []
    for pno, lines in parsed:
        name_x, desc_x, status_x = cols.get(pno, med)
        for words in lines:
            left = [(x, t) for x, t in words if x < name_x - 40]
            if not left:
                continue
            star = any("*" in t for _, t in left)
            code = re.sub(r"[^0-9A-Z]", "", "".join(t.upper() for _, t in left))
            m = CUSIP_OCR.match(code)
            if not m:
                continue
            name = [t for x, t in words if name_x - 40 <= x < desc_x - 40]
            desc = [t for x, t in words if desc_x - 40 <= x < status_x - 40]
            status = [t for x, t in words if x >= status_x - 40]
            cusip = code              # as read; never corrected
            rows.append({"quarter": yq, "cusip": cusip, "issuer_name": " ".join(name).upper(),
                         "issue_description": " ".join(desc).upper(), "status": norm_status(" ".join(status)),
                         "raw_line": " ".join(t for _, t in words), "has_options": "Y" if star else "",
                         "page": pno, "source": "ocr", "check_digit_ok": "Y" if cusip_ok(cusip) else "N"})
    missing_hdr = len(parsed) - len(cols)
    if missing_hdr:
        notes.append(f"{yq}: {missing_hdr} of {len(parsed)} OCR pages had no readable header; "
                     f"used the quarter's median columns")
    return rows


# --------------------------------------------------------------------------- combined lookup
def qkey(yq: str) -> tuple[int, int]:
    return int(yq[:4]), int(yq[5])


def build_lookup(rows: list[dict], notes: list[str]) -> list[dict]:
    names: dict[str, dict[str, list]] = defaultdict(dict)       # cusip -> name -> [first, last, sources]
    descs: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if is_option(r["issue_description"]):
            continue
        if r["source"] == "ocr" and r["check_digit_ok"] != "Y":
            continue
        c, nm = r["cusip"], r["issuer_name"].strip()
        if not nm:
            continue
        rec = names[c].setdefault(nm, [r["quarter"], r["quarter"], set()])
        rec[0] = min(rec[0], r["quarter"], key=qkey)
        rec[1] = max(rec[1], r["quarter"], key=qkey)
        rec[2].add(r["source"])
        if r["issue_description"]:
            descs[c][r["issue_description"]] += 1

    pairs: dict[tuple[str, str], dict] = {}
    for fn in FTD_FILES:
        path = OUT / fn
        if not path.exists():
            notes.append(f"lookup: {fn} not found (run fetch_sec_holdings.py"
                         f"{' --ftd-from 2004-01' if '2004' in fn else ''}); its tickers are absent")
            continue
        with path.open(newline="") as fh:
            for r in csv.DictReader(fh):
                if fn == "ftd_cusip_symbol.csv" and r["first_seen"] >= FTD_MODERN_BEFORE:
                    continue
                k = (r["cusip"], r["symbol"])
                if k not in pairs:
                    pairs[k] = dict(r)
                else:
                    p = pairs[k]
                    p["first_seen"] = min(p["first_seen"], r["first_seen"])
                    if r["last_seen"] >= p["last_seen"]:
                        p["last_seen"], p["description"] = r["last_seen"], r["description"]
    syms: dict[str, list[dict]] = defaultdict(list)
    for p in pairs.values():
        syms[p["cusip"]].append(p)

    out = []
    for c in sorted(set(names) | set(syms)):
        nm = sorted(names.get(c, {}).items(), key=lambda kv: (qkey(kv[1][0]), kv[0]))
        sy = sorted(syms.get(c, []), key=lambda p: (p["first_seen"], p["symbol"]))
        out.append({
            "cusip": c, "cusip6": c[:6],
            "issue_descriptions": " | ".join(d for d, _ in descs[c].most_common()),
            "issuer_names": " | ".join(f"{n} [{a}..{b}{'' if 'text' in s else ' ocr'}]" for n, (a, b, s) in nm),
            "name_first_quarter": min((v[0] for _, v in nm), key=qkey) if nm else "",
            "name_last_quarter": max((v[1] for _, v in nm), key=qkey) if nm else "",
            "symbols": " | ".join(f"{p['symbol']} [{p['first_seen']}..{p['last_seen']}"
                                  f"{' placeholder' if p['placeholder'] else ''}]" for p in sy),
            "symbol_first_seen": min((p["first_seen"] for p in sy), default=""),
            "symbol_last_seen": max((p["last_seen"] for p in sy), default=""),
            "ftd_descriptions": " | ".join(dict.fromkeys(p["description"] for p in sy)),
            "name_sources": "+".join(sorted({s for _, (_, _, ss) in nm for s in ss})),
        })
    return out


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
    for tool in ("pdftotext", "pdfinfo"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} (poppler) not found")
    CACHE.mkdir(parents=True, exist_ok=True)
    sec = Sec(args.offline)
    pdfs, missing = fetch_pdfs(sec)
    notes: list[str] = []
    rows: list[dict] = []
    for yq, pdf in sorted(pdfs.items(), key=lambda kv: qkey(kv[0])):
        if is_scanned(pdf):
            if not (shutil.which("tesseract") and shutil.which("pdftoppm")):
                notes.append(f"{yq}: scanned PDF and tesseract/pdftoppm not installed; skipped")
                continue
            q_rows = parse_ocr(yq, ocr_quarter(yq, pdf), notes)
        else:
            q_rows = parse_text_pdf(yq, pdf, notes)
        rows.extend(q_rows)
        real = [r for r in q_rows if not is_option(r["issue_description"])]
        bad = sum(r["check_digit_ok"] != "Y" for r in real)
        log(f"{yq}: {len(q_rows)} lines ({q_rows[0]['source'] if q_rows else '-'}), "
            f"{len(real)} non-option, {bad} of them fail the CUSIP check digit")
    write_csv(OUT / "13f_list_2002_2010.csv", LIST_COLS, rows)
    log(f"13f_list_2002_2010.csv: {len(rows)} rows; quarters missing: {missing or 'none'}")

    lookup = build_lookup(rows, notes)
    write_csv(OUT / "cusip_name_symbol_2002_2010.csv", LOOKUP_COLS, lookup)
    both = sum(1 for r in lookup if r["issuer_names"] and r["symbols"])
    log(f"cusip_name_symbol_2002_2010.csv: {len(lookup)} CUSIPs; with a 13(f) name "
        f"{sum(1 for r in lookup if r['issuer_names'])}, with a fails ticker "
        f"{sum(1 for r in lookup if r['symbols'])}, both {both}")
    for n in notes:
        log(f"note: {n}")
    log(f"{sec.requests} requests to sec.gov")
    return 0


if __name__ == "__main__":
    sys.exit(main())
