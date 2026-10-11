# S&P 500 point-in-time membership

Built by `build_sp500_membership.py` into schema `usmarket` on `localhost:5434/market_pulse`.
Tables follow `market_pulse.index_membership` (NSE), so the same queries work.

## Coverage

**1999-01-04 to 2002-11-29 only.** The files in this repo give nothing outside it. Use
`usmarket.index_membership_coverage` to check, and `usmarket.index_members_on()`, which
returns no rows outside coverage instead of a stale roster.

| Source | Role |
|---|---|
| S&P change lists 1999, 2000, 2001, 2002 (to 18 Nov), Wayback captures | Every addition and deletion, "effective after close of trading" |
| S&P `500alpha.csv` | The one full list. Captured 2002–03 but its contents are the composition effective **2001-06-04**, found from the change lists with 0 contradictions |
| SPDR Trust N-30D, 30 Sep 2001 | Cross-check only (a fund's list, names only; RESEARCH.md decision 1) |

## Results of the checks

- Rolling S&P's 304 add/delete rows back to Jan 1999 and forward to Nov 2002 from
  `500alpha.csv` gives **0 contradictions** (no delete of a non-member, no add of a member).
- Every snapshot holds 500 members, except 8 stretches at 499. In each, S&P printed a
  deletion with no same-day addition and a later one-sided addition restored 500.
- SPDR's 30 Sep 2001 holdings: 491 of 500 match by name automatically. The other 9 pair
  off one-to-one with 9 SPDR names that are the same companies written differently
  (DuPont, FirstEnergy, Freddie Mac, Limited, PerkinElmer, QLogic, Tyco, US Airways,
  UnumProvident).

Only the `500alpha.csv` snapshot is `is_verified`. The rest follow from S&P's own notices,
but no second S&P list closes the loop.

## Reused tickers

Eight continuing members changed ticker (`usmarket.index_symbol_change`). Four took the
ticker of a company S&P deleted the same day (HON, JPM, USB, WB), and ATI took AirTouch's
ticker some time after its 1999 deletion. Snapshots and
`vw_index_membership_spells` are keyed by ticker, so a spell for one of these tickers can
span two companies. Join through `index_symbol_change` before joining prices.

Three renames are dated by S&P's own notes. The others are placed at the earliest change
date the files allow, which moves only the ticker label, never membership. Tickers not
printed in these files (old ALD, CMB, FSR, ALT; First Union's new WB) come from general
knowledge and say so in `note`.

## Queries

```sql
-- Members on a day
select * from usmarket.index_members_on('SP500', '2000-03-10');

-- When was a ticker in the index
select * from usmarket.vw_index_membership_spells where symbol = 'ENE';

-- What S&P changed, with its own dates
select after_close_date, effective_date, action, symbol, company
from usmarket.index_change_event order by after_close_date;

-- Every check, passed or not
select * from usmarket.index_membership_reconciliation order by check_date;
```

`effective_date` is the first trading day of the new composition (the trading day after
S&P's "after close" date, on the NYSE calendar, including the 11–14 Sep 2001 closure).

## Rebuild

```bash
python3 sp500_history/membership/build_sp500_membership.py --dry-run   # parse and check only
python3 sp500_history/membership/build_sp500_membership.py             # replace the SP500 rows
```

`USMARKET_DSN` overrides the connection. The script applies `schema.sql` first and is safe
to rerun.

## Extending past 2002

The method takes more anchors and more notices without changing the tables. The next
sources, in RESEARCH.md order:

1. Fund full lists (Vanguard/Fidelity/Schwab N-CSR and N-Q, month-end from Jul 2004;
   N-PORT data sets from 2019 with CUSIP and ticker). Needs the owner's decision 1.
2. S&P notices: PR Newswire Feb 2010–2011; S&P Global's press archive from Jan 2012.
3. 2003–2009 stays weak: the one 2007 S&P page and company IR copies.
