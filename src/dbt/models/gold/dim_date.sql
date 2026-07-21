-- Calendar spine, hard-bounded to both generators' shared rand_ts() window
-- (2026-01-01..2026-06-15, confirmed identical in generate_events.py and
-- generate_multiline.py) -- 166 rows. No source dependency: every fact's
-- event_date is guaranteed to fall in this range because DLQ rows (null /
-- epoch-zero / far-future sentinels) are quarantined before _clean, so the
-- event_date -> dim_date relationships test can never fail on an out-of-range
-- date.

select
    date_day,
    year(date_day) as year,
    quarter(date_day) as quarter,
    month(date_day) as month,
    date_format(date_day, 'MMMM') as month_name,
    day(date_day) as day_of_month,
    dayofweek(date_day) as day_of_week,   -- Spark: 1 = Sunday .. 7 = Saturday
    date_format(date_day, 'EEEE') as day_name,
    weekofyear(date_day) as week_of_year,
    dayofweek(date_day) in (1, 7) as is_weekend
from (
    select explode(sequence(date('2026-01-01'), date('2026-06-15'), interval 1 day)) as date_day
)
