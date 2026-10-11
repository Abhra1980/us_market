# FRED data

US macro and market series from FRED (Federal Reserve Bank of St. Louis), loaded into schema
`usmarket` on `localhost:5434/market_pulse`. Full history, latest vintage.

```sql
select * from usmarket.vw_fred_latest;                                    -- latest value of each series
select obs_date, value from usmarket.fred_observation where series_id = 'DGS10' order by obs_date;
select series_id, category, title, units, copyright from usmarket.fred_series order by category;
```

## Load

```bash
export FRED_API_KEY="..."              # per person, from fredaccount.stlouisfed.org; never in git
python3 fred/load_fred.py              # every series in fred/series.csv (~2 minutes)
python3 fred/load_fred.py DGS10 UNRATE # just these
python3 fred/load_fred.py --dry-run    # fetch and report, write nothing
```

Each series is replaced in full in its own transaction. To add a series, add a line to
`series.csv` (`series_id,category,why`) and rerun for it.

## What is loaded

94 series in 17 groups: Treasury curve, policy rates, real rates and inflation expectations,
credit, inflation, labour, growth, households, housing, money and the Fed, financial conditions,
dollar and FX, commodities, recession indicators, equity indices, valuation inputs, government.

## Copyright

FRED republishes some series by permission of their owners. FRED's notes for each series say so,
and the loader follows them:

| Series | Owner | What is stored |
|---|---|---|
| SP500, DJIA | S&P Dow Jones Indices | Description only: "reproduction ... prohibited except with the prior written permission" |
| BAMLC0A0CM, BAMLH0A0HYM2 | ICE Data Indices | Description only, same wording |
| CSUSHPINSA | S&P (Case-Shiller) | Values, flagged in `copyright` ("Reprinted with permission") |
| VIXCLS | Cboe | Values, flagged |
| UMCSENT, MICH | University of Michigan | Values, flagged |
| NASDAQCOM | Nasdaq | Values, flagged |
| MORTGAGE30US | Freddie Mac | Values, flagged |
| PCOPPUSDM | IMF | Values, flagged |

Port 5434 also feeds public dashboards (RESEARCH.md decision 4). Check `fred_series.copyright`
before showing a series publicly.
