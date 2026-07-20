-- Generic across ALL event types, reused by every v0.2 event-family slice.
-- Dedup + envelope-level drift resolution, plus customer_id_resolved (shared
-- by 9 of the 10 event types -- payout.scheduled is the one exception, it has
-- no customer key at all, so this resolves to NULL for that type by design).
-- payload itself is passed through untouched; payload-specific fixes are each
-- event family's own job (see int_transactions.sql and friends).

with deduped as (
    select
        *,
        row_number() over (
            partition by event_id
            -- ingested_at is a string; cast to timestamp before ordering —
            -- raw string comparison is unsafe when ISO fractional-second
            -- width varies (Python's isoformat() omits ".NNNNNN" when
            -- microseconds == 0), which can sort inconsistently.
            order by try_cast(ingested_at as timestamp) desc, _ingested_at desc
        ) as rn
    from {{ ref('stg_raw_events') }}
),

resolved as (
    select
        event_id,
        event_type,
        schema_version,
        ingested_at,
        event_timestamp,
        -- Envelope timestamp drift: v1 = epoch millis, v2 = ISO-8601 string,
        -- both delivered under the same JSON key -- Bronze's schema
        -- inference collapses that the same way it collapsed payload.risk,
        -- so event_timestamp is a STRING column regardless of which version
        -- produced it. Unify to one TIMESTAMP column.
        case
            when event_timestamp is null then null
            when schema_version = '1.0' then timestamp_millis(try_cast(event_timestamp as bigint))
            when schema_version = '2.0' then try_cast(event_timestamp as timestamp)
        end as resolved_event_timestamp,
        -- Source drift: v1 flat string `source_system`, v2 struct `source`.
        case when schema_version = '2.0' then source.system else source_system end as resolved_source_system,
        case when schema_version = '2.0' then source.region else null end as resolved_source_region,
        case when schema_version = '2.0' then source.host else null end as resolved_source_host,
        -- Key renaming (v1 cust_id vs v2 customer_id) -- both fields exist as
        -- nullable siblings in Bronze's inferred payload struct for every
        -- event type; exactly one is populated per row, except payout.scheduled
        -- (merchant-centric, no customer key at all -- resolves to NULL there).
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
    ingested_at,
    event_timestamp,
    resolved_event_timestamp,
    -- Flags the 3 sentinel values generate_events.py's build_envelope()
    -- injects on purpose (null / epoch-zero 1970-01-01 / far-future
    -- 2099-12-31). Compared against the RESOLVED timestamp, not the raw
    -- event_timestamp column -- comparing the raw column would miss every
    -- v1-encoded sentinel (~35% of defect rows), since v1 delivers
    -- epoch-millis ints while v2 delivers ISO strings for the same key.
    -- Exact-literal match is safe and collision-free: rand_ts() is
    -- hard-bounded to 2026-01-01..2026-06-15 (data/generators/generate_events.py),
    -- so a legitimate event timestamp can never land on either sentinel.
    case
        when resolved_event_timestamp is null then 'null'
        when resolved_event_timestamp = timestamp('1970-01-01T00:00:00Z') then 'epoch_zero'
        when resolved_event_timestamp = timestamp('2099-12-31T00:00:00Z') then 'far_future'
        else 'ok'
    end as event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    resolved_source_host,
    customer_id_resolved,
    payload,
    _source_file,
    _ingested_at
from resolved
