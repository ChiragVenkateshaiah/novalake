-- Scoped to refund.issued in the multiline file. Fields are top-level
-- payload siblings here too (no "refund" wrapper key), confirmed against
-- data/generators/generate_multiline.py's build_refund. amount is
-- genuinely nullable by generator design (maybe(...)) -- passed through
-- as-is.

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

    payload.original_transaction_id as original_transaction_id,
    payload.amount as amount,
    payload.currency as currency_raw,
    {{ clean_currency('payload.currency') }} as currency_clean,
    payload.reason as reason,
    payload.partial as partial,

    _source_file,
    _ingested_at
from {{ ref('int_multiline_events_deduped') }}
where event_type = 'refund.issued'
