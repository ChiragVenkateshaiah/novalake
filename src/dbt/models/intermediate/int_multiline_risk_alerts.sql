-- Scoped to risk.alert in the multiline file. Same shape as the NDJSON
-- file's int_risk_alerts, plus signals[].sub_signals[] -- a new
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

    payload.alert_type as alert_type,
    payload.severity as severity,
    payload.signals as signals,
    payload.notes as notes,
    payload.auto_blocked as auto_blocked,

    _source_file,
    _ingested_at
from {{ ref('int_multiline_events_deduped') }}
where event_type = 'risk.alert'
