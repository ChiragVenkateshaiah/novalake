-- Scoped to support.ticket only. No payload drift beyond
-- customer_id_resolved. description is free text -- kept as-is, this is the
-- field the eventual GenAI layer will index, not something to "clean".
-- related_transaction_id and resolution_minutes are genuinely nullable by
-- generator design (maybe(...)) -- passed through as-is.
-- tags[] and messages[] both stay arrays here; exploded downstream off the
-- clean model, as two independent siblings (not nested) -- exploding both
-- in one query would cross-join them, which is wrong.

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

    payload.ticket_id as ticket_id,
    payload.channel as channel,
    payload.priority as priority,
    payload.subject as subject,
    payload.description as description,
    payload.tags as tags,
    payload.related_transaction_id as related_transaction_id,
    payload.messages as messages,
    payload.resolved as resolved,
    payload.resolution_minutes as resolution_minutes,

    _source_file,
    _ingested_at
from {{ ref('int_events_deduped') }}
where event_type = 'support.ticket'
