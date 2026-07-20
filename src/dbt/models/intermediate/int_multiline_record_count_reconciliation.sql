-- Compares export_metadata.record_counts.events (per page) against the
-- PRE-DEDUP int_multiline_events row count for that page -- not the
-- deduped count. Verified against data/generators/generate_multiline.py's
-- build_page(): `reported = len(events) + choice([-3,-1,0,0,2,5])` is
-- computed from `events` AFTER the ~1.5% within-page replays are appended,
-- so len(events) already includes them -- comparing against a deduped
-- count would contaminate the generator's intentional reconciliation delta
-- with an unrelated dedup effect. Surfaces the (by-design) delta; does not
-- "fix" it, there's nothing to fix.
--
-- record_counts.customers/.merchants are always-null STRING columns (the
-- generator sets them to None unconditionally -- confirmed via a real
-- `describe`) -- not reconciled here, there's no real data to compare.
--
-- Event and failure counts are pre-aggregated to page grain in their own
-- CTEs before joining -- joining the two unaggregated exploded tables
-- directly on `page` would fan out (every event paired with every failure
-- on that page), silently inflating both counts.

with events_per_page as (
    select page, count(*) as actual_events
    from {{ ref('int_multiline_events') }}
    group by page
),

failures_per_page as (
    select page, count(*) as actual_partial_failures
    from {{ ref('int_multiline_partial_failures') }}
    group by page
)

select
    s.pagination.page as page,
    s.export_metadata.record_counts.events as reported_events,
    coalesce(e.actual_events, 0) as actual_events,
    s.export_metadata.record_counts.events - coalesce(e.actual_events, 0) as events_delta,
    s.export_metadata.record_counts.partial_failures as reported_partial_failures,
    coalesce(f.actual_partial_failures, 0) as actual_partial_failures
from {{ ref('stg_raw_events_multiline') }} s
left join events_per_page e on e.page = s.pagination.page
left join failures_per_page f on f.page = s.pagination.page
