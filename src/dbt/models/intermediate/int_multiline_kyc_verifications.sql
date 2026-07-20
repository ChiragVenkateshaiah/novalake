-- Scoped to kyc.verification in the multiline file. Same shape as the
-- NDJSON file's int_kyc_verifications, plus documents[].pages[] -- a new
-- two-level nesting not present in the NDJSON version.

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

    payload.full_name as full_name,
    payload.status as status,
    payload.risk_score as risk_score,
    payload.documents as documents,

    _source_file,
    _ingested_at
from {{ ref('int_multiline_events_deduped') }}
where event_type = 'kyc.verification'
