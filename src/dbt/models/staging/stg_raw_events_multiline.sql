-- Thin pass-through over Bronze's multiline landing table, mirroring
-- stg_raw_events.sql. One row per page (9 expected). No explode/flatten
-- here -- that's int_multiline_events.sql / int_multiline_partial_failures.sql.

select
    export_metadata,
    pagination,
    reference_data,
    data,
    audit,
    _source_file,
    _ingested_at
from {{ source('bronze', 'raw_events_multiline') }}
