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
| 1999-01-04 → 2002-11-29 | S&P's 1999–2002 change lists rolled from S&P's own full list `500alpha.csv` (June 2001) | SPDR's Sep 2001 holdings: 491 of 500 by name automatically, the last 9 paired by eye | June 2001 snapshot only |
| **2003 → 2009** | **No answer.** `index_members_on()` returns no rows | | |
| 2010-01-04 → 2019-09-30 | S&P's press releases rolled back from the Sep 2019 fund lists | Every member traded under its ticker near each date (SEC fails data) | No |
| 2019-10-01 → today | S&P's press releases rolled from the 30 Jun 2026 fund lists | Fund holdings at all 83 month-ends Sep 2019–Jul 2026: 68 match exactly | Where the month-ends on both sides match |

Every membership change comes from S&P's text. Fund lists only check it (RESEARCH.md decision 1,
accepted 2026-10-12). Where S&P's archive has no release, the change is listed in the build
script with its evidence and labelled in `note`.

## Builds

```bash
python3 sp500_history/membership/fetch_sp_press.py          # S&P releases -> data/*.csv (cached)
python3 sp500_history/membership/fetch_sec_holdings.py      # SEC NPORT-P + fails data (cached; sec.gov)
python3 sp500_history/membership/build_sp500_membership.py  # 1999-2002 rows
python3 sp500_history/membership/build_sp500_modern.py      # 2010 onward rows
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
| `sec_cusip_symbol` | SEC fails-to-deliver CUSIP ↔ ticker pairs 2009–2026, with first and last sighting. Join prices through this |
| `index_source_file` | Where each source came from |

- **S&P press releases 2010–2026** (`fetch_sp_press.py` → `data/sp500_changes_2010_2026.csv`,
  `data/sp500_ticker_changes_2010_2026.csv`): S&P Global's archive from 2012, PR Newswire 2010–11.
- **SEC Form NPORT-P** for SPY, Vanguard 500, Fidelity 500, Schwab S&P 500 and IVV: a full list at
  every month-end from Sep 2019. Funds file CUSIPs, not tickers.
- **SEC fails-to-deliver files 2009–2026**: which ticker each CUSIP traded under, and when.
  Names fund holdings, dates ticker changes, and dates S&P's "date to be announced" changes.
- **SEC EDGAR** company records: a renamed company keeps its CIK, which links old and new tickers
  when the CUSIP also changed (Torchmark → Globe Life, Priceline → Booking, …).

## What the checks found

- **Roll contradictions: 0.** No addition of a member or deletion of a non-member, 1999–2002 or
  2010–2026.
- **Fund month-ends: 68 of 83 match exactly.** The other 15 are fund-side timing, recorded as is:
  spin-offs S&P adds on distribution day (Fortrea, Veralto, Solventum, Qnity, FedEx Freight),
  spin-off shares funds keep briefly (Embecta, Millrose, Amentum, Ralliant), deals closing at a
  month-end (Citrix, Duke Realty, IHS Markit), rights and warrants, and a same-week ticker change.
- Schwab's fund holds one Fox and one News Corp line from Oct 2023; its month-ends are checked
  with FOX and NWS excused, and say so in `note`.
- 2010–2019 has no fund list in this build. Every member traded under its ticker within 120 days
  of each snapshot, except old Fox's one-day tickers TFCF/TFCFA (19 Mar 2019).

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

## Extending to 2003–2009

S&P's own notices are scarce for these years (RESEARCH.md §1). The route is month-end fund lists
from SEC N-Q/N-CSR filings (from mid-2004, names only, no CUSIPs), matched to tickers by name.
