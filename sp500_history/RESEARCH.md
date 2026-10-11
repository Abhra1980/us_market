# S&P 500 history: where to get it

Research only, 2026-10-11. Nothing has been built, bought or loaded. This says where
point-in-time S&P 500 membership, the index's total return and every member's total
return can come from, what each source costs, how it fits CLAUDE.md §1 (primary sources
only), and what the owner has to decide before the database is built on the data PC
(CLAUDE.md §4, at Abhrajit's location).

## The answer

| What | Best route | Coverage | Cost | Blocker |
|---|---|---|---|---|
| **Membership** | S&P's own change notices, rolled between full holdings lists that S&P 500 index funds file with the SEC | Fund lists from 1993; S&P notices 1999–2002 and 2010 onward; 2003–2009 weak | Free | Owner: accept the fund filings as checkpoints |
| **Index total return** (SPXT) | S&P DJI's own export | 2016-09-30 onward (10 years only) | Free to view | S&P's terms forbid storing it in a database without written permission |
| **Member total returns** | CRSP if anyone has institutional access; else Sharadar under a commercial licence | CRSP 1925 onward; Sharadar 1998 onward | CRSP: institution only; Sharadar commercial: quote | No free source has delisted stocks; personal licences forbid a shared database; the owner's 2026-10-05 plan says "no new data purchases" |

So membership can be built now for nothing. The two return series cannot be built from
free primary sources: one needs S&P's permission, the other a purchase.

## Decisions for the owner

1. **Fund filings as membership checkpoints.** They are the funds' regulatory filings,
   not S&P's own file, so using them would be a recorded exception like the Kotak and
   Moneycontrol ones. Every membership change itself would still come from S&P's own text.
2. **Member returns: buy or stop.** Choices, best first:
   - CRSP, if anyone can get it through a university or employer;
   - Sharadar through Nasdaq Data Link's commercial licence (ask for a quote);
   - FirstRate Data, a one-time $499.95 that allows several users, but has no membership
     data and admits gaps in delisted names;
   - none, and stop at membership plus index return.
3. **Index return.** Ask S&P DJI for written permission to store the export, or keep it
   in files outside the database and use it only to check our own numbers.
4. **Where the data lives.** 5434 is read by the public dashboards over the tunnel
   (CLAUDE.md §2). S&P and vendor terms make a separate database or schema on the data PC,
   which no site reads, the safer home.
5. **A contact for SEC requests.** `www.sec.gov` refuses requests that don't declare who
   is asking ("Undeclared Automated Tool"); its fair-access policy wants a name and an
   email in the User-Agent, and at most 10 requests a second. The capture job needs one.

## 1. Membership

### Full holdings lists filed with the SEC

Full-replication S&P 500 funds file their complete holdings. Since 2003 Form N-CSR
Item 6 requires the full schedule even when the shareholder report shows only a summary
([Form N-CSR](https://www.sec.gov/files/formn-csr.pdf)).

| Fund | CIK | Forms and period-ends | Holdings complete in (checked) |
|---|---|---|---|
| SPDR S&P 500 ETF Trust (SPY) | 884394 | N-30D: Dec 1995/1996, then Sep yearly to 2009; Mar and Sep 2010–2019; NPORT-P quarterly from Sep 2019 | 2001 (parsed: about 490 rows before fixing wrapped names) |
| Vanguard 500 Index | 36405 | N-30D Jun/Dec from Dec 1993; N-CSR(S) Dec/Jun from 2003; N-Q Mar/Sep 2004–2018; NPORT-P | Dec 1994, Dec 2004, Mar 2013, Dec 2012, Dec 2017 |
| Fidelity 500 Index (formerly Spartan 500) | 819118 | N-30D Feb/Aug from 1996; N-CSR Feb, N-CSRS Aug; N-Q May/Nov 2004–2018 | Feb 2001 says "a complete list"; Feb 2013 complete |
| Schwab S&P 500 Index | 904333 | N-CSR Oct, N-CSRS Apr; N-Q Jan/Jul 2004–2019 | Jul 2004 N-Q; the Oct 2012 report is condensed, with the full list in N-CSR |
| iShares Core S&P 500 (IVV) | 1100663 | N-30D Mar/Sep from Sep 2000; N-CSR(S); N-Q Jun/Dec 2004–2018 | Sep 2000. Later years not checked: 22–48 MB multi-fund filings |
| Vanguard Institutional Index | 862084 | Same dates as Vanguard 500 | Dec 1994, Jun 2005 (506 stocks); a cross-check only |

How often there is a full list, combining the funds:

| Period | Full lists |
|---|---|
| 1993–1995 | Twice a year (Vanguard Jun/Dec), plus SPY at year-end |
| 1996 to mid-2004 | At least one every quarter (Fidelity Feb/Aug, Vanguard Jun/Dec, SPY Sep, IVV Mar/Sep from 2000) |
| Jul 2004 to 2019 | Every month-end (Schwab Jan/Apr/Jul/Oct, Fidelity Feb/May/Aug/Nov, Vanguard Mar/Jun/Sep/Dec) |
| 2019 onward | NPORT-P each fund quarter; month-end coverage should continue but is not confirmed |

From 2019 the SEC's [Form N-PORT data sets](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets)
(quarterly zips, 2019 Q4 to 2026 Q3) carry each holding's name, CUSIP, LEI, ISIN and
ticker ([readme](https://www.sec.gov/files/nport_readme.pdf)), so no HTML parsing is
needed there.

### S&P's own change notices

| Years | Where S&P's own text survives | Share of the year's changes |
|---|---|---|
| Before 1999 | Nothing found online | ~0% |
| 1999–2002 | Wayback copies of S&P's index site: year-by-year change lists with effective dates and tickers ("all changes effective after close of trading"): 1999 44 rows, 2000 60, 2001 32, 2002 to 18 Nov 24. Also S&P's full constituent file `500alpha.csv` (2001–02) and its A–Z list pages (1999–2000) | ~100%; 2002 ~95% (December missing) |
| 2003–2009 | One 2007 S&P page "Implemented Index Additions and Deletions" (8,583 rows across all S&P indices, with a download link); copies of releases on company IR sites | Low, not measured |
| Feb 2010–2011 | [PR Newswire's S&P page](https://www.prnewswire.com/news/standard-%26-poor%27s/) | Likely high, not counted |
| Jan 2012 onward | [S&P Global's press archive](https://press.spglobal.com/index.php?s=2429&l=100) (paged by `o=`; the oldest page reaches 5 Jan 2012) | High |

Example 1999–2002 page:
`https://web.archive.org/web/20021031132956/http://www.spglobal.com/indexmain500_changes00.html`.
A capture date is not an as-of date: `500alpha.csv` is byte-identical from Feb 2002 to
Jan 2003 although S&P changed the index in July 2002.

The S&P DJI site today shows only the top 10 members; its "Full Constituents List" sends
users to SPICE, the paid data portal. EDGAR full-text search finds only 0–3 company 8-Ks
a year quoting S&P's replacement notices (2001–2011), so 8-Ks will not fill 2003–2009.

### Why a fund's list can differ from the index

Reconciliation has to record these, never smooth them over:

- Line counts differ: Vanguard 500 held 506 stocks when the index had 505 (Dec 2017).
- Futures, cash and securities-lending collateral appear as lines (Vanguard E-mini
  futures; Schwab "Other Investment Companies 5.9%", Jul 2004).
- Timing: IVV's 30 Sep 2000 list still holds Owens Corning, which S&P deleted after
  the close on 29 Sep 2000.
- Spin-off shares held until sold, rights, and cash-out mergers are expected but no filed
  case was found.

### Identifiers

Before 2019 every list gives names only, with share classes as separate lines ("Comcast
Corp. Class A" and "Special Class A"). Matching names across years is the main work.

- S&P's notices give tickers.
- The SEC's [Official List of Section 13(f) Securities](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/official-list-section-13f-securities),
  quarterly from 1996, maps issuer names to CUSIPs.
- From 2019 the N-PORT data sets give CUSIP, ISIN and ticker directly.
- `company_tickers.json` has no history and does not help.

### Method

This is `backtesting/backend/universe/build_event_membership.py` with S&P in place of NSE:

1. take two consecutive full lists A and B;
2. apply S&P's notices effective after A and on or before B;
3. write daily membership as verified only where the result equals B exactly;
4. leave every other stretch carried forward from A and disclose it.

With month-end lists from Jul 2004, an unproven stretch is at most about a month, but
the day a change took effect stays unknown in it and must not be guessed.

## 2. Index total return

| Series | Source | First date | Access |
|---|---|---|---|
| S&P 500 TR (SPXT, indexId 344) | S&P DJI | First value 1989-09-11 per S&P's page | Export, last 10 years only |
| S&P 500 Net TR (indexId 2383) | S&P DJI | Launched 2009-04-20, back-filled to 1998-12-31 | Export, 10 years |
| S&P 500 Dividend Points, quarterly (indexId 386) | S&P DJI | 1990 | Export, 10 years |
| S&P 500 price (SPX, indexId 340) | S&P DJI | Launched 1957-03-04 | Export, 10 years; Wayback copies reach 2011-04-29 |
| S&P 500 TR, monthly | S&P DJI | 1936, cited in an S&P paper | Not downloadable; SPICE is the paid route |
| Yahoo `^SP500TR` | Copy | 1988-01-04 | Free, needs checks (below) |
| CRSP `vwretd` on S&P 500 members | Independent | 1925 | WRDS (institution) |
| SBBI large-cap, Shiller, Damodaran | Independent | 1926 monthly / 1871 monthly / 1928 annual | Free or yearbook; approximate |

- **S&P's website export.** The `yearFlag` options run up to `tenYearFlag`; `yearFlag=all`
  gives the same 10 years for the TR. The export URL's Wayback captures (759) include no
  TR file at all, so stitching cannot extend the TR.
- **S&P's terms.** Terms of use §4.2: S&P DJI data is "solely for non-commercial, personal
  use", and may not be used "to create … historical databases". Every export's footer
  forbids storing it "in a database or retrieval system, without the prior written
  permission of S&P DJI".
- **S&P's formula** ([Index Mathematics](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-index-math.pdf)).
  Dividends are reinvested across the index at the close on the ex-date:
  - DTR_t = (Price_t + IndexDividend_t) / Price_{t−1} − 1
  - TR_t = TR_{t−1} × (1 + DTR_t)
- **Checked.** [`checks/rebuild_tr_from_dividend_points.py`](checks/rebuild_tr_from_dividend_points.py)
  rebuilds 10 years of TR (2016-09-30 to 2026-10-09, 2,520 days, 40 quarterly resets) from
  S&P's price export and its dividend points export.
  - It ends at 17,525.41 against S&P's 17,525.23.
  - No day is off by more than 0.13 bp.
  - The inputs are not in the repo, because S&P's terms forbid it.
- **Yahoo `^SP500TR` against S&P's export.**
  - 10 of 2,520 days differ by more than 0.005.
  - Stale prints: 2019-03-12 (0.30% low) and 2019-07-03 (0.59% low).
  - A −1.8%/+1.9% glitch on 1990-01-24/25.
  - Nothing official covers 1988-01-04 to 1989-09-08 to check it against.
- **SPY as a cross-check.** SPY's NAV return trails S&P's TR by about 15 bp a year (fee
  plus cash held until the quarterly payout), so SPY checks the TR only to a few bp a year.

## 3. Member total returns

Every free source with deep history (Yahoo, Stooq) lacks delisted stocks, so a free
route would be survivorship-biased. That is the CLAUDE.md §1 failure again.

Prices are from the vendors' pages on 2026-10-10.

| Route | S&P 500 membership from | Prices incl. delisted from | Raw dividend and split events | Delisting returns | Cost (USD) | Shared 2-person database |
|---|---|---|---|---|---|---|
| CRSP (WRDS or CRSP direct; Morningstar bought CRSP in Feb 2026) | 1925 (daily list) | 1925 | Yes | **Yes, the only one** | Quote; institutions only | Under the institution's licence |
| Sharadar via Nasdaq Data Link | Jan 1998 ("Deep history to 1998") | Dec 1997 | Yes (ACTIONS table) | Merger terms for ~99% of mergers, plus delisting reasons; nothing for bankruptcies | Personal $299/yr; commercial: quote | **Personal: no** ("individuals only"; data deleted 30 days after cancelling). Commercial: ask |
| Norgate Platinum / Diamond | 1957 | 1990 / 1950 ("essentially complete back to late 1992") | No split events; total return computed by Norgate | No | $630 / $787.50 a year | **No** ("one individual natural person"; no "shared … multi-user environment" unless Norgate agrees). Windows only |
| FirstRate Data | None | 2000; "over 7000 delisted", "not the complete universe" | Yes | No | $499.95 once; updates $59.95/mo | Yes ("multiple users … within a single corporation") |
| EODHD | Continuous from Apr 2012 only | Delisted before 2018: prices only | Not for pre-2018 delistings | No | Business $3,990/seat, server download not included; Enterprise $24,990 | Enterprise only |
| Tiingo | None | 30+ years; delisted unverified | Yes | No | $499 internal commercial | Unclear |
| Massive (was Polygon.io) | None | "20+ years" | Yes | No | Business $2,499/mo | Business tier only |
| QuantConnect | n/a | 1998 | Yes | No | $2,136 + updates | **No**: usable only inside their engine |
| Terminals (Bloomberg, LSEG, FactSet, Capital IQ) | Yes | Yes | Yes | Varies | ~$12k–32k per user per year (third-party estimates) | Bulk export doubtful |

- **Compustat** no longer carries S&P's constituent history: S&P removed it in July 2020.
- **Delisting returns matter.**
  - Shumway (1997) found the correct returns missing for most stocks delisted for bad
    news; the usual fix is −30% on NYSE/AMEX, about −55% on Nasdaq.
  - For S&P 500 members the bias is smaller, since most leave by deletion while still
    trading or by a merger with known terms.
  - It is concentrated in members that failed while in the index (Enron 2001, Lehman 2008).
- **How to compute total return.** Our rule (one reviewed adjustments table, CLAUDE.md §1)
  favours raw close plus dividend and split events over a vendor's adjusted series. CRSP,
  Sharadar and FirstRate supply those; Norgate does not.

## 4. How the data will check itself

- **Membership:** every stretch between two fund lists either reproduces the next list or
  is disclosed. Mega-caps present every year, and the member count stays at about 500
  securities (505 with share classes), as `test_pit_universe_integrity.py` does for NSE.
- **Member returns against the index:**
  - weight members by their share counts in a full-replication fund's list (SPY's shares
    held are proportional to index weights);
  - compound the members' total returns;
  - compare with SPXT over 2016–2026.
  - A gap means a member, a price or a dividend is wrong.
- **Index TR:** price plus dividend points reproduces S&P's TR (above). Before 2016,
  compare with CRSP `vwretd` if CRSP is bought.

## Not verified

- IVV's lists after 2000; whether month-end coverage continues after 2019.
- 2003–2009 S&P notices beyond the one 2007 page; Business Wire's archive.
- Where S&P's "Full Constituents List" link leads.
- Vendor prices that need a quote:
  - Sharadar commercial;
  - CRSP;
  - Norgate multi-user.
- Sharadar's S&P 500 table: daily changes or quarterly snapshots (its pages say both).
- Tiingo and Massive delisted coverage.
- Whether any vendor licenses its S&P 500 list from S&P DJI.
- SPXT's base value.
