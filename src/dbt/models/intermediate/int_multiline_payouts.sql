-- Scoped to payout.scheduled in the multiline file. No customer_id_resolved
-- (merchant-centric, same as the NDJSON file). No bank_account_last4 here --
-- confirmed against data/generators/generate_multiline.py's build_payout,
-- which genuinely differs field-by-field from the NDJSON generator's
-- build_payout even for "the same" event type.

select
    event_id,
    event_type,
    schema_version,
    page,
    resolved_event_timestamp,
    event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,

    payload.merchant_id as merchant_id,
    payload.gross_amount as gross_amount,
    payload.currency as currency_raw,
    {{ clean_currency('payload.currency') }} as currency_clean,
    payload.schedule as schedule,
    payload.line_breakdown as line_breakdown,

    _source_file,
    _ingested_at
from {{ ref('int_multiline_events_deduped') }}
where event_type = 'payout.scheduled'
