-- Point-in-time S&P 500 membership, schema usmarket (localhost:5434/market_pulse).
-- Same shape as market_pulse.index_membership (NSE) so the two can be queried alike.
-- Idempotent: build_sp500_membership.py runs this before every load.

create schema if not exists usmarket;

-- Every file a row came from, with where and when it was captured.
create table if not exists usmarket.index_source_file (
    source        text primary key,              -- short id, e.g. 'sp_changes_2000'
    publisher     text not null,                 -- 'S&P' or the fund that filed it
    kind          text not null check (kind in ('change_list', 'constituent_list', 'fund_holdings')),
    path          text not null,                 -- path inside the us_market repo
    url           text,                          -- original URL (Wayback for S&P's old site)
    captured_on   date,                          -- capture date; NOT the as-of date
    note          text
);

-- S&P's own additions and deletions. S&P dates them "effective after close of trading".
create table if not exists usmarket.index_change_event (
    event_id          bigserial primary key,
    index_type        text not null,             -- 'SP500'
    after_close_date  date not null,             -- the date S&P printed
    effective_date    date not null,             -- first trading day of the new composition
    action            text not null check (action in ('include', 'exclude')),
    symbol            text not null,
    company           text not null,
    source            text not null references usmarket.index_source_file (source),
    note              text,
    unique (index_type, after_close_date, action, symbol)
);
create index if not exists index_change_event_date on usmarket.index_change_event (index_type, effective_date);

-- Ticker changes for a continuing member, so a rename is not read as a delete + add.
create table if not exists usmarket.index_symbol_change (
    index_type      text not null,
    effective_date  date not null,
    old_symbol      text not null,
    new_symbol      text not null,
    company         text not null,
    source          text not null references usmarket.index_source_file (source),
    note            text,
    primary key (index_type, effective_date, old_symbol)
);

-- Full lists used as checkpoints (S&P's own) or cross-checks (fund holdings, names only).
create table if not exists usmarket.index_constituent_list (
    source      text not null references usmarket.index_source_file (source),
    line_no     integer not null,
    index_type  text not null,
    as_of_date  date not null,                   -- see as_of_basis: may be inferred
    as_of_basis text not null,
    symbol      text,                            -- null where the list gives names only
    company     text not null,
    industry    text,
    primary key (source, line_no)
);

-- One full snapshot per composition change; a snapshot holds until the next one.
-- is_verified = true only where S&P's own full list confirms that exact composition.
create table if not exists usmarket.index_membership (
    index_type      text not null,
    effective_date  date not null,
    symbol          text not null,
    source          text not null,
    is_verified     boolean not null default false,
    primary key (index_type, effective_date, symbol)
);
create index if not exists idx_us_membership_symbol on usmarket.index_membership (symbol);
create index if not exists idx_us_membership_date on usmarket.index_membership (effective_date);

-- The stretch of days the snapshots are known to describe. Outside it: no answer.
create table if not exists usmarket.index_membership_coverage (
    index_type       text not null,
    covered_from     date not null,
    covered_through  date not null,
    basis            text not null,
    primary key (index_type, covered_from)
);

-- Every check the build ran, passed or not. Failures are recorded, never smoothed.
create table if not exists usmarket.index_membership_reconciliation (
    index_type    text not null,
    check_name    text not null,
    check_date    date not null,
    reconciled    boolean not null,
    expected      integer,
    actual        integer,
    missing       text[] not null default '{}',
    extra         text[] not null default '{}',
    note          text,
    checked_at    timestamptz not null default now(),
    primary key (index_type, check_name, check_date)
);

-- Members on a day: the latest snapshot on or before it, only inside coverage.
create or replace function usmarket.index_members_on(p_index text, p_day date)
returns table (symbol text, snapshot_date date, source text, is_verified boolean)
language sql stable as $$
    select m.symbol, m.effective_date, m.source, m.is_verified
    from usmarket.index_membership m
    where m.index_type = p_index
      and exists (select 1 from usmarket.index_membership_coverage c
                  where c.index_type = p_index and p_day between c.covered_from and c.covered_through)
      and m.effective_date = (select max(effective_date) from usmarket.index_membership
                              where index_type = p_index and effective_date <= p_day)
$$;

-- One row per continuous stretch of membership. end_date is the last day as a member;
-- null means still a member when coverage ends.
create or replace view usmarket.vw_index_membership_spells as
with snap as (
    select index_type, effective_date,
           lead(effective_date) over (partition by index_type order by effective_date) as next_date,
           dense_rank() over (partition by index_type order by effective_date) as snap_no
    from (select distinct index_type, effective_date from usmarket.index_membership) d
), runs as (
    select m.index_type, m.symbol, m.effective_date, s.next_date, m.is_verified,
           s.snap_no - row_number() over (partition by m.index_type, m.symbol order by m.effective_date) as grp
    from usmarket.index_membership m
    join snap s using (index_type, effective_date)
)
select index_type, symbol,
       min(effective_date) as start_date,
       case when bool_or(next_date is null) then null else max(next_date) - 1 end as end_date,
       count(*) as snapshots,
       bool_or(is_verified) as touches_verified_list
from runs
group by index_type, symbol, grp;
