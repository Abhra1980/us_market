-- FRED series for the us_market project, schema usmarket (localhost:5434/market_pulse).
-- Idempotent: load_fred.py runs this before every load.

create schema if not exists usmarket;

-- One row per series in fred/series.csv, with FRED's own description of it.
create table if not exists usmarket.fred_series (
    series_id            text primary key,
    category             text not null,            -- our grouping, from series.csv
    title                text,
    frequency            text,
    units                text,
    seasonal_adjustment  text,
    observation_start    date,
    observation_end      date,
    last_updated         timestamptz,              -- when FRED last updated the series
    notes                text,                     -- FRED's notes, including any copyright text
    restricted           boolean not null default false,  -- publisher forbids reproduction: values not stored
    restricted_reason    text,
    copyright            text,                     -- third-party copyright line from FRED's notes, if any
    observations         integer not null default 0,     -- rows held in fred_observation
    loaded_at            timestamptz not null default now()
);

-- Values as FRED publishes them today (the latest vintage). FRED's "." (no value) is null.
create table if not exists usmarket.fred_observation (
    series_id  text not null references usmarket.fred_series (series_id) on delete cascade,
    obs_date   date not null,
    value      double precision,
    primary key (series_id, obs_date)
);
create index if not exists fred_observation_date on usmarket.fred_observation (obs_date);

-- Latest value of each stored series.
create or replace view usmarket.vw_fred_latest as
select s.series_id, s.category, s.title, s.frequency, s.units, o.obs_date, o.value
from usmarket.fred_series s
join lateral (select obs_date, value from usmarket.fred_observation o
              where o.series_id = s.series_id and o.value is not null
              order by obs_date desc limit 1) o on true
order by s.category, s.series_id;

alter table usmarket.fred_series add column if not exists copyright text;
