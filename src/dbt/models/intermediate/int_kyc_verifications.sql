-- Scoped to kyc.verification only. No payload drift beyond
-- customer_id_resolved -- risk_score here is unrelated to
-- transaction.risk (0-100 float, always populated, no collapse issue).
-- documents[] stays an array here; exploded downstream off the clean model
-- (int_kyc_documents.sql) since it's guaranteed non-empty by construction
-- (randint(1,3)) -- plain explode, no explode_outer needed.

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

    payload.full_name as full_name,
    payload.status as status,
    payload.risk_score as risk_score,
    payload.documents as documents,

    _source_file,
    _ingested_at
from {{ ref('int_events_deduped') }}
where event_type = 'kyc.verification'
