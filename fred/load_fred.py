#!/usr/bin/env python3
"""Load the FRED series listed in fred/series.csv into schema usmarket.

THE SOURCE
----------
FRED, Federal Reserve Bank of St. Louis (https://fred.stlouisfed.org), through its API.
The key is read from the environment, never from the repo (it is public):
    export FRED_API_KEY="..."

THE RULES
---------
* Full history of each series, latest vintage (the values FRED shows today).
* Some series belong to publishers who forbid reproduction without permission (S&P DJI's
  indices, some ICE, Cboe and University of Michigan data). FRED says so in the series notes.
  For those, only the description is stored, flagged ``restricted``, with the reason; the
  values are not, because port 5434 also feeds public dashboards (RESEARCH.md decision 4).
* Each series is replaced in full in its own transaction, so a failed series leaves the
  previous load of it intact.

Usage:
    python3 fred/load_fred.py                 # every series in series.csv
    python3 fred/load_fred.py DGS10 UNRATE    # just these
    python3 fred/load_fred.py --dry-run       # fetch and report, write nothing
    python3 fred/load_fred.py --changed-only  # skip series FRED has not updated since the last load (daily job)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_DSN = "postgresql://abhrajitpal@127.0.0.1:5434/market_pulse"
HERE = Path(__file__).resolve().parent
API = "https://api.stlouisfed.org/fred"
MIN_INTERVAL = 0.6          # FRED allows 120 requests a minute; stay well under
# FRED notes that say the publisher must give permission before the data is reproduced.
RESTRICTED = re.compile(r"(reproduction|redistribution|reproduce|redistribute)[^.]{0,120}"
                        r"(prohibited|not permitted|without (the )?(prior )?(express )?(written )?permission)"
                        r"|permission (is )?required", re.I)

_last = 0.0


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


def fred(path: str, **params) -> dict:
    """GET one FRED API call, throttled, with polite retries."""
    global _last
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise SystemExit('Set FRED_API_KEY (export FRED_API_KEY="..."); it is never stored in the repo')
    url = f"{API}/{path}?" + urllib.parse.urlencode({**params, "api_key": key, "file_type": "json"})
    for attempt in range(5):
        time.sleep(max(0.0, _last + MIN_INTERVAL - time.time()))
        _last = time.time()
        try:
            return json.load(urllib.request.urlopen(url, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt * 5)
                continue
            body = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"FRED {path} {params.get('series_id')}: HTTP {e.code} {body[:200]}") from None
    raise RuntimeError("unreachable")


def restriction(notes: str) -> str | None:
    """The sentence of FRED's notes that forbids reproduction, if any."""
    m = RESTRICTED.search(notes or "")
    if not m:
        return None
    start = max((notes or "").rfind(".", 0, m.start()) + 1, 0)
    end = (notes or "").find(".", m.end())
    return (notes or "")[start: end + 1 if end != -1 else None].strip()[:500]


def copyright_line(notes: str) -> str | None:
    """Third-party copyright named in FRED's notes ("Copyright, 2016, Chicago Board Options Exchange...")."""
    m = re.search(r"Copyright[^.\n]*", notes or "")
    return re.sub(r"\s+", " ", m.group(0).replace("Â", "")).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("series", nargs="*", help="only these series ids (default: all in series.csv)")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    ap.add_argument("--changed-only", action="store_true",
                    help="skip series whose FRED last_updated equals the stored one")
    ap.add_argument("--dsn", default=os.environ.get("USMARKET_DSN") or DEFAULT_DSN)
    args = ap.parse_args()

    wanted = list(csv.DictReader((HERE / "series.csv").open()))
    if args.series:
        wanted = [w for w in wanted if w["series_id"] in set(args.series)]
        missing = set(args.series) - {w["series_id"] for w in wanted}
        if missing:
            raise SystemExit(f"not in fred/series.csv: {sorted(missing)} (add them there first)")

    conn = None
    if not args.dry_run:
        import psycopg2  # noqa: PLC0415
        from psycopg2.extras import execute_values  # noqa: PLC0415
        conn = psycopg2.connect(args.dsn)
        with conn, conn.cursor() as cur:
            cur.execute((HERE / "schema.sql").read_text())

    stored = {}
    if conn and args.changed_only:
        with conn.cursor() as cur:
            cur.execute("select series_id, last_updated from usmarket.fred_series")
            stored = dict(cur.fetchall())

    loaded, restricted, failed, unchanged = [], [], [], []
    for w in wanted:
        sid = w["series_id"]
        try:
            meta = fred("series", series_id=sid)["seriess"][0]
            if sid in stored and stored[sid] and \
                    datetime.fromisoformat(meta["last_updated"].replace(" ", "T")) == stored[sid]:
                unchanged.append(sid)
                continue
            reason = restriction(meta.get("notes", ""))
            obs = [] if reason else fred("series/observations", series_id=sid, limit=100000)["observations"]
        except Exception as e:  # noqa: BLE001 - one bad series must not stop the rest
            failed.append((sid, str(e)[:200]))
            log(f"FAILED {sid}: {str(e)[:200]}")
            continue
        rows = [(sid, o["date"], None if o["value"] == "." else float(o["value"])) for o in obs]
        if reason:
            restricted.append((sid, meta["title"], reason))
            log(f"restricted {sid:16} {meta['title'][:60]} -> description only")
        else:
            loaded.append((sid, len(rows)))
            log(f"{sid:16} {len(rows):>6} obs  {meta['observation_start']} .. {meta['observation_end']}  "
                f"{meta['title'][:60]}")
        if conn:
            with conn, conn.cursor() as cur:
                cur.execute("delete from usmarket.fred_series where series_id = %s", (sid,))
                cur.execute("""insert into usmarket.fred_series
                    (series_id, category, title, frequency, units, seasonal_adjustment, observation_start,
                     observation_end, last_updated, notes, restricted, restricted_reason, observations, copyright)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (sid, w["category"], meta.get("title"), meta.get("frequency"), meta.get("units"),
                     meta.get("seasonal_adjustment"), meta.get("observation_start"), meta.get("observation_end"),
                     meta.get("last_updated"), meta.get("notes"), bool(reason), reason, len(rows),
                     copyright_line(meta.get("notes", ""))))
                if rows:
                    execute_values(cur, "insert into usmarket.fred_observation (series_id, obs_date, value) values %s",
                                   rows, page_size=10000)

    log(f"done: {len(loaded)} series loaded ({sum(n for _, n in loaded)} observations), "
        f"{len(unchanged)} unchanged since the last load, "
        f"{len(restricted)} restricted (description only), {len(failed)} failed")
    for sid, title, why in restricted:
        log(f"   restricted {sid}: {why[:160]}")
    for sid, err in failed:
        log(f"   failed {sid}: {err}")
    if conn:
        conn.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
