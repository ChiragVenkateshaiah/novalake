-- First-level explode of the multiline export: one row per event
-- (~4,000+ rows expected across 9 pages). Sibling to
-- int_multiline_partial_failures.sql -- exploding both from the same
-- staging row in one query would cross-join them, which is wrong.
--
-- page (pagination.page) is carried through so downstream work can trace
-- an event back to its source page -- needed for the cross-page
-- reference-data joins in a later increment.
--
-- No dedup/envelope-drift resolution here yet (unlike int_events_deduped
-- for the NDJSON file) -- this event's envelope shape differs (no
-- ingested_at field at all, confirmed against
-- data/generators/generate_multiline.py's build_event()), so it needs its
-- own resolution model, designed in a later increment once this one's
-- output is in hand.

select
    p.pagination.page as page,
    event_index,
    event.event_id,
    event.event_type,
    event.schema_version,
    event.event_timestamp,
    event.source,
    event.source_system,
    event.payload,
    p._source_file,
    p._ingested_at
from {{ ref('stg_raw_events_multiline') }} p
lateral view posexplode(p.data.events) exploded_events as event_index, event
