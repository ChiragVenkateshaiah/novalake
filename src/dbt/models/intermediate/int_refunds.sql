-- Scoped to refund.issued only. currency needs clean_currency (same dirty
-- pool as transaction.*); customer_id_resolved from the generic layer.
-- `amount` and `notes` are both genuinely nullable by generator design
-- (maybe(...)) -- passed through as-is, not a defect to fix.

select
    event_id,
    event_type,
    schema_version,
    resolved_event_timestamp,
    event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    resolved_source_host,
    customer_id_resolved,

    payload.original_transaction_id as original_transaction_id,
    payload.amount as amount,
    payload.currency as currency_raw,
    {{ clean_currency('payload.currency') }} as currency_clean,
    payload.reason as reason,
    payload.partial as partial,
    payload.notes as notes,

    _source_file,
    _ingested_at
from {{ ref('int_events_deduped') }}
where event_type = 'refund.issued'
