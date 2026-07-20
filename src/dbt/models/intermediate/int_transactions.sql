-- Scoped to transaction.{completed,failed,created} only. Payload-level
-- drift resolution for this event family. line_items stays an array here --
-- explode happens downstream, after the DLQ split (int_transaction_line_items.sql).

with risk_parsed as (
    select
        *,
        from_json(payload.risk, 'score double, flagged boolean, reasons array<string>') as risk_struct
    from {{ ref('int_events_deduped') }}
    where event_type in ('transaction.completed', 'transaction.failed', 'transaction.created')
)

select
    event_id,
    event_type,
    schema_version,
    resolved_event_timestamp,
    event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    resolved_source_host,

    -- Key renaming (v1 cust_id vs v2 customer_id) -- both fields exist as
    -- nullable siblings in Bronze's inferred payload struct; exactly one is
    -- populated per row.
    coalesce(payload.customer_id, payload.cust_id) as customer_id_resolved,

    -- Unit + type drift: v1 `amount` (major-unit float, always populated),
    -- v2 `amount_minor` (minor-unit int, always populated, ~10% delivered
    -- as a string -- try_cast handles both underlying types safely).
    case
        when schema_version = '2.0' then try_cast(payload.amount_minor as bigint)
        when schema_version = '1.0' then try_cast(round(payload.amount * 100) as bigint)
    end as amount_minor_resolved,

    -- Dirty categorical: casing/whitespace recover via upper+trim. "US$" is
    -- the one genuinely invalid CURRENCIES_DIRTY value (data/generators/
    -- generate_events.py) and will NOT match a clean code -- kept visible
    -- via currency_clean, not silently discarded (see the warn-severity
    -- test in _intermediate.yml).
    payload.currency as currency_raw,
    upper(trim(payload.currency)) as currency_clean,

    -- Dirty categorical requiring alias mapping, not just case/trim.
    -- Mapping verified against the generator's actual COUNTRIES list:
    -- US/USA/United States -> US, GB/uk -> GB, IN/India -> IN,
    -- CA/Canada -> CA; JP/DE/FR pass through unchanged; null stays null.
    payload.country as country_raw,
    case
        when payload.country is null then null
        when upper(trim(payload.country)) in ('US', 'USA', 'UNITED STATES') then 'US'
        when upper(trim(payload.country)) in ('GB', 'UK') then 'GB'
        when upper(trim(payload.country)) in ('IN', 'INDIA') then 'IN'
        when upper(trim(payload.country)) in ('CA', 'CANADA') then 'CA'
        else upper(trim(payload.country))
    end as country_clean,

    -- risk: struct collapsed to STRING at Bronze for ALL rows (well-formed
    -- rows are valid JSON *text*, the ~3% malformed rows are literal
    -- "score=X" text) -- recover via from_json for the well-formed rows,
    -- regex fallback for the malformed ones. str(round(x,3)) in the
    -- generator always emits a decimal point, so the regex is safe.
    coalesce(
        risk_struct.score,
        try_cast(regexp_extract(payload.risk, 'score=([0-9]+\\.[0-9]+)', 1) as double)
    ) as risk_score,
    risk_struct.flagged as risk_flagged,   -- null for malformed rows: never recoverable from the string
    risk_struct.reasons as risk_reasons,   -- null for malformed rows: never recoverable from the string
    risk_struct.score is null as risk_malformed,  -- score is never null in well-formed rows

    payload.merchant as merchant,
    payload.payment_method as payment_method,
    payload.status as status,
    payload.idempotency_key as idempotency_key,
    payload.line_items as line_items,     -- untouched; exploded downstream

    _source_file,
    _ingested_at
from risk_parsed
