-- First-level explode of the multiline export's dead-letter records:
-- one row per partial_failures[] entry, sibling to int_multiline_events.sql
-- (not nested inside it -- these are independent arrays off the same page
-- row). `raw` is a stringified (escaped) JSON blob of a genuinely broken
-- event -- kept as-is here (from_json parsing of it is later work, once
-- this quarantine table's shape is confirmed); never joined into the clean
-- event pipeline.

select
    p.pagination.page as page,
    failure_index,
    failure.failure_id,
    failure.stage,
    failure.error_code,
    failure.raw,
    failure.attempted_at,
    failure.retryable,
    p._source_file,
    p._ingested_at
from {{ ref('stg_raw_events_multiline') }} p
lateral view posexplode(p.data.partial_failures) exploded_failures as failure_index, failure
