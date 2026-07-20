-- Scoped to transaction.{completed,failed,created} in the multiline file.
-- Payload nests one level deeper here (payload.transaction.*) than the
-- NDJSON file's flat payload.* -- verified against a real `describe` on
-- Bronze's inferred schema, not assumed. balances/metadata (dynamic-key
-- maps) stay untouched here; reconstructed as MAP in Increment 6.
-- line_items/fees/network_tokens stay arrays here; exploded in Increment 6.

with risk_parsed as (
    select
        *,
        -- risk collapsed to STRING at Bronze, same mechanism as the NDJSON
        -- file's payload.risk (well-formed rows are valid JSON text, ~3%
        -- malformed rows are literal "score=X" text). Schema now also
        -- includes signal_matrix (array-of-arrays -- a construct not seen
        -- in the NDJSON slice), confirmed a valid Spark DDL type string.
        from_json(
            payload.transaction.risk,
            'score double, flagged boolean, reasons array<string>, signal_matrix array<array<double>>'
        ) as risk_struct
    from {{ ref('int_multiline_events_deduped') }}
    where event_type in ('transaction.completed', 'transaction.failed', 'transaction.created')
)

select
    event_id,
    event_type,
    schema_version,
    page,
    resolved_event_timestamp,
    event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    customer_id_resolved,

    payload.transaction.merchant_id as merchant_id,

    -- Unit + type drift: same pattern as the NDJSON file's amount/amount_minor.
    case
        when schema_version = '2.0' then try_cast(payload.transaction.amount_minor as bigint)
        when schema_version = '1.0' then try_cast(round(payload.transaction.amount * 100) as bigint)
    end as amount_minor_resolved,

    payload.transaction.currency as currency_raw,
    {{ clean_currency('payload.transaction.currency') }} as currency_clean,

    payload.country as country_raw,
    {{ clean_country('payload.country') }} as country_clean,

    coalesce(
        risk_struct.score,
        try_cast(regexp_extract(payload.transaction.risk, 'score=([0-9]+\\.[0-9]+)', 1) as double)
    ) as risk_score,
    risk_struct.flagged as risk_flagged,
    risk_struct.reasons as risk_reasons,
    risk_struct.signal_matrix as risk_signal_matrix,
    risk_struct.score is null as risk_malformed,

    payload.transaction.payment_method as payment_method,
    payload.transaction.line_items as line_items,
    payload.transaction.fees as fees,
    payload.status as status,
    payload.idempotency_key as idempotency_key,
    payload.balances as balances,
    payload.metadata as metadata,

    _source_file,
    _ingested_at
from risk_parsed
