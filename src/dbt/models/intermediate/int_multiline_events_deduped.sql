-- Generic across ALL event types in the multiline file, mirroring
-- int_events_deduped's role for the NDJSON file -- but NOT unified with it
-- (see docs/02-silver.md's "Known design calls": the multiline envelope has
-- no ingested_at field at all, and payload shapes are already incompatible
-- between the two sources for the same conceptual event type).
--
-- Dedup tie-break: replays within a page are byte-identical
-- json.loads(json.dumps(...)) copies (data/generators/generate_multiline.py's
-- build_page()), so any deterministic pick is correct -- ordering by the
-- partition key itself is a valid, information-free tie-break in Spark SQL.
--
-- Note: `source` here has no `host` field (unlike the NDJSON file's source
-- struct) -- confirmed via a real `describe` on the Bronze-inferred schema,
-- not assumed.

with deduped as (
    select
        *,
        row_number() over (
            partition by event_id
            order by event_id
        ) as rn
    from {{ ref('int_multiline_events') }}
),

resolved as (
    select
        event_id,
        event_type,
        schema_version,
        page,
        event_timestamp,
        case
            when event_timestamp is null then null
            when schema_version = '1.0' then timestamp_millis(try_cast(event_timestamp as bigint))
            when schema_version = '2.0' then try_cast(event_timestamp as timestamp)
        end as resolved_event_timestamp,
        case when schema_version = '2.0' then source.system else source_system end as resolved_source_system,
        case when schema_version = '2.0' then source.region else null end as resolved_source_region,
        -- Key renaming (v1 cust_id vs v2 customer_id) -- same generic
        -- promotion as int_events_deduped, verified safe here too (both
        -- fields exist as nullable siblings across the merged payload union).
        coalesce(payload.customer_id, payload.cust_id) as customer_id_resolved,
        payload,
        _source_file,
        _ingested_at
    from deduped
    where rn = 1
)

select
    event_id,
    event_type,
    schema_version,
    page,
    event_timestamp,
    resolved_event_timestamp,
    -- Same 3-sentinel logic and collision-safety reasoning as
    -- int_events_deduped -- rand_ts() here is also hard-bounded to
    -- 2026-01-01..2026-06-15 (data/generators/generate_multiline.py).
    case
        when resolved_event_timestamp is null then 'null'
        when resolved_event_timestamp = timestamp('1970-01-01T00:00:00Z') then 'epoch_zero'
        when resolved_event_timestamp = timestamp('2099-12-31T00:00:00Z') then 'far_future'
        else 'ok'
    end as event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    customer_id_resolved,
    payload,
    _source_file,
    _ingested_at
from resolved
