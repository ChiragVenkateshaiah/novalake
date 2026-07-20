-- Scoped to support.ticket in the multiline file. Nested under
-- payload.ticket.* here, unlike the NDJSON file's flat payload.* --
-- confirmed against a real `describe`. sla is a stable struct (no drift).
-- metadata is a genuine dynamic-key map here too (support.ticket's own
-- dyn_metadata() call, sharing the same union column as
-- transaction.metadata) -- reconstructed as MAP for the same
-- open-vocabulary reason.

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

    payload.ticket.ticket_id as ticket_id,
    payload.ticket.channel as channel,
    payload.ticket.priority as priority,
    payload.ticket.subject as subject,
    payload.ticket.description as description,
    payload.ticket.tags as tags,
    payload.ticket.related_transaction_id as related_transaction_id,
    payload.ticket.messages as messages,
    payload.ticket.sla as sla,
    from_json(to_json(payload.metadata), 'map<string,string>') as metadata_map,

    _source_file,
    _ingested_at
from {{ ref('int_multiline_events_deduped') }}
where event_type = 'support.ticket'
