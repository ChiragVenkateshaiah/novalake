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

    -- Dynamic-key-map fields, reconstructed as actual MAP<STRING,STRING>
    -- (to_json + from_json round-trip) rather than left as Bronze's inferred
    -- bounded struct. Both are the principled cases per docs/02-silver.md:
    -- `metadata` has open-vocabulary, descriptive keys (dyn_metadata() --
    -- the genuine schema-explosion case the dataset guide is teaching, only
    -- bounded here because this generator's META_KEYS pool happens to be
    -- finite); `balances` is lookup-keyed (currency codes used downstream).
    -- Spark's from_json coerces the struct's mixed-type values (int, float,
    -- string, bool) to their string form when the target value type is
    -- STRING -- verified at dbt run time, not assumed.
    from_json(to_json(payload.metadata), 'map<string,string>') as metadata_map,
    from_json(to_json(payload.balances), 'map<string,string>') as balances_map,

    _source_file,
    _ingested_at
from risk_parsed
