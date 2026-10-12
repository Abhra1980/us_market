# S&P 500 point-in-time membership

Schema `usmarket` on `localhost:5434/market_pulse`. Main table: **`usmarket.index_membership`**,
same shape as the NSE `market_pulse.index_membership`.

```sql
select * from usmarket.index_members_on('SP500', '2020-12-21');        -- members on a day
select * from usmarket.vw_index_membership_spells where symbol = 'TSLA'; -- when a ticker was in
select * from usmarket.index_membership_coverage order by covered_from;  -- which days have an answer
```

## Coverage

| Stretch | How it is built | Checked by | `is_verified` |
|---|---|---|---|
| 1999-01-04 → 2002-11-29 | S&P's 1999–2002 change lists and its 2000–2002 name and ticker change pages, rolled from S&P's own full list `500alpha.csv` (June 2001) | SPDR's Sep 2001 holdings: 491 of 500 by name automatically, the last 9 paired by eye | June 2001 snapshot only |
| 2002-11-30 → 2010-01-03 | S&P's own "Implemented Index Additions and Deletions" table (complete July 2002 – Nov 2009 by S&P's printed row count), its releases and ticker-change table, rolled forward from Nov 2002 | Arrives exactly at the 4 Jan 2010 list the 2010 build rolls back to; fund holdings by name at 79 month-ends (129 lists): 59 confirmed, the rest explained, no cross-fund suspects | Between two confirmed month-ends |
| 2010-01-04 → 2019-09-30 | S&P's press releases rolled back from the Sep 2019 fund lists | Fund holdings by name (N-CSR/N-Q) at 111 month-ends (197 lists): 96 confirmed, the rest explained, no cross-fund suspects; every member traded under its ticker near each date (SEC fails data) | Between two confirmed month-ends |
| 2019-10-01 → today | S&P's press releases rolled from the 30 Jun 2026 fund lists | Fund holdings at all 83 month-ends Sep 2019–Jul 2026: 68 match exactly | Where the month-ends on both sides match |

Every membership change comes from S&P's text. Fund lists only check it (RESEARCH.md decision 1,
accepted 2026-10-12). Where S&P's archive has no release, the change is listed in the build
script with its evidence and labelled in `note`.

## Builds

```bash
python3 sp500_history/membership/fetch_sp_press.py          # S&P releases -> data/*.csv (cached)
python3 sp500_history/membership/fetch_sec_holdings.py      # SEC NPORT-P + fails data (cached; sec.gov)
python3 sp500_history/membership/fetch_sp_press_2003_2009.py        # S&P 2003-2009 pages (Wayback) -> data/*_2003_2009.csv
python3 sp500_history/membership/fetch_sec_fundlists_2002_2009.py   # fund N-CSR/N-Q schedules 2002-2010 (sec.gov)
python3 sp500_history/membership/fetch_sec_fundlists_2002_2009.py --from 2010-04-30 --to 2019-09-30   # ... 2010-2019
python3 sp500_history/membership/fetch_sec_13f_lists.py             # SEC 13(f) lists 2002-2010 (sec.gov; OCR for 2002-03 scans)
python3 sp500_history/membership/fetch_sec_holdings.py --ftd-from 2004-03   # SEC fails data Mar 2004 - Jun 2009
python3 sp500_history/membership/build_sp500_membership.py  # 1999 to Nov 2002 rows
python3 sp500_history/membership/build_sp500_modern.py      # 2010 onward rows
python3 sp500_history/membership/build_sp500_2003_2009.py   # Dec 2002 - 2009 rows; run last (starts and ends on the other two)
```

Each build has `--dry-run`, replaces only its own rows, and can be rerun. `USMARKET_DSN` overrides
the connection. The SEC fetcher needs `export SEC_USER_AGENT="Your Name you@example.com"` (the SEC
requires a contact; it is sent to sec.gov only), or `--offline` to use cached files. Raw downloads
go to `sp500_history/downloads/` (not in git).

## Sources and tables

| Table | What |
|---|---|
| `index_membership` | One full snapshot per composition change; holds until the next |
| `index_change_event` | S&P's additions and deletions with `announced_date`, `release_url` and S&P's sentence |
| `index_symbol_change` | Ticker changes of members, each with its evidence (S&P, fund lists, SEC fails data, EDGAR) |
| `index_constituent_list` | S&P's June 2001 list, SPDR 2001, and every fund month-end 2019–2026 with CUSIP, ISIN and how many funds held it |
| `index_membership_reconciliation` | Every check run, passed or not |
| `sec_cusip_symbol` | SEC fails-to-deliver CUSIP ↔ ticker pairs 2004–2026, with first and last sighting. Join prices through this |
| `index_source_file` | Where each source came from |

- **S&P press releases 2010–2026** (`fetch_sp_press.py` → `data/sp500_changes_2010_2026.csv`,
  `data/sp500_ticker_changes_2010_2026.csv`): S&P Global's archive from 2012, PR Newswire 2010–11.
- **SEC Form NPORT-P** for SPY, Vanguard 500, Fidelity 500, Schwab S&P 500 and IVV: a full list at
  every month-end from Sep 2019. Funds file CUSIPs, not tickers.
- **SEC fails-to-deliver files 2004–2026**: which ticker each CUSIP traded under, and when (before 16 Sep 2008 only securities with fails of 10,000 shares or more).
  Names fund holdings, dates ticker changes, and dates S&P's "date to be announced" changes.
- **SEC EDGAR** company records: a renamed company keeps its CIK, which links old and new tickers
  when the CUSIP also changed (Torchmark → Globe Life, Priceline → Booking, …).

## What the checks found

- **Roll contradictions: 0.** No addition of a member or deletion of a non-member, 1999 to today.
- **Fund month-ends 2019–2026: 68 of 83 match exactly.** The other 15 are fund-side timing, recorded as is:
  spin-offs S&P adds on distribution day (Fortrea, Veralto, Solventum, Qnity, FedEx Freight),
  spin-off shares funds keep briefly (Embecta, Millrose, Amentum, Ralliant), deals closing at a
  month-end (Citrix, Duke Realty, IHS Markit), rights and warrants, and a same-week ticker change.
- Schwab's fund holds one Fox and one News Corp line from Oct 2023; its month-ends are checked
  with FOX and NWS excused, and say so in `note`.
- 2010–2019 is checked against the funds' N-CSR/N-Q lists by name (98 of 197 exact, 96 of 111
  month-ends confirmed) and every member traded under its ticker within 120 days of each
  snapshot, except old Fox's one-day tickers TFCF/TFCFA (19 Mar 2019).

## Things to know before using it

- **Tickers are reused** (JPM, HON, IR, CEG, ACT, Q, SII, LIN…). Snapshots and spells are by
  ticker, so join prices through `index_symbol_change` and `sec_cusip_symbol` at the date, not by
  ticker alone.
- Ticker changes S&P did not date are dated by the SEC fails data (first day the new ticker
  appears). That can be a few days off; it moves the label, never membership.
- Changes with no S&P press release (Mylan → Viatris, WestRock → Smurfit Westrock, Paramount →
  Paramount Skydance, ITT → Xylem, Smith International → Tyco, Praxair → Linde, Comcast's CMCSK
  line, Under Armour's class C line, and renames with a new CUSIP) are lists in
  `build_sp500_modern.py`, each with its evidence. A few links are general knowledge and say so.

## 2003–2009

- **S&P's text.** S&P's old S&P 500 page carried a table "Implemented Index Additions and
  Deletions (all changes effective after close of trading)". Stitched from about 244 Wayback
  captures, it holds every row S&P counted (310 of 310 as of Oct 2009) back to July 2002. S&P's
  release PDFs, its portal notices and PR Newswire copies add announcement dates. Where a release
  and the table disagree by a few days (7 changes), the table is used and the release is kept as
  `superseded` in the CSV.
- **One change from outside S&P's pages:** Roper Industries for ENSCO, effective 23 Dec 2009,
  from S&P's wording as Briefing.com carried it on 22 Dec 2009. Every fund list of 31 Dec 2009
  agrees (`NO_NOTICE` in `build_sp500_2003_2009.py`).
- **Ticker changes:** S&P's "Name and Ticker Changes" tables (2000–2009), then the SEC fails data
  (same CUSIP, new ticker: E*TRADE ET → ETFC, Safeco SAFC → SAF, Waste Management WMI → WM).
- **Fund lists** (Vanguard 500, Vanguard Institutional, Fidelity Spartan, Schwab S&P 500, SPY,
  IVV): names only, matched to tickers through the SEC's fails data (from Mar 2004) and 13(f)
  lists (from 2002 Q4). Every month-end from Jul 2004 has at least one complete list; before that,
  quarterly or half-yearly. Each difference is labelled in `index_membership_reconciliation`:
  timing around an S&P date (funds buy additions days early and keep deletions until a deal
  closes), a stock kept after S&P deleted it, a stock handed over in a deal or spin-off (Tronox B,
  Teva for Barr, McClatchy for Knight Ridder), or a member the fund did not hold (Schwab lagged
  the index by months in early 2007).
- **Matching names to tickers:** the SEC's issuer name as of each date (`ftd_cusip_names*.csv`,
  written by `fetch_sec_holdings.py`), the 13(f) lists, S&P's own company names, and every name a
  member's CUSIPs and former tickers carried before (Fidelity printed "MGM Mirage" in 2018).
  Another share class of a member, and an old name on the same CUSIP, are not differences.
- **Cross-fund check:** a member one fund lacks must be held by another fund within 45 days, and
  a non-member every fund holds would mean a missing addition. Both lists are empty for
  2003–2009 and for 2010–2019 (`cross_fund_suspects` in the reconciliation table).
- **Results:** 0 roll contradictions; the roll lands on the 2010 build's 4 Jan 2010 list with
  all 500 members equal; 54 of 129 fund lists match exactly and 59 of 79 month-ends are
  confirmed. Counts below 500 (14 days, e.g. Fannie Mae and Freddie Mac, Sep 2008) are S&P
  deleting a member before naming its replacement.
- **Earlier years corrected:** S&P's 2000–2002 ticker pages now date the 1999–2002 build's ticker
  changes (Wyeth, HP, ConocoPhillips, CenterPoint, ChevronTexaco, Countrywide…) in place of the
  general-knowledge placements it had.
