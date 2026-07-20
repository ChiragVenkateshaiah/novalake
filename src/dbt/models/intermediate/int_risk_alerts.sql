-- Scoped to risk.alert only. No payload drift beyond customer_id_resolved.
-- signals[] stays an array here; exploded downstream off the clean model
-- (int_risk_alert_signals.sql), guaranteed non-empty by construction
-- (randint(1,4)) -- plain explode, no explode_outer needed.

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

    payload.alert_type as alert_type,
    payload.severity as severity,
    payload.signals as signals,
    payload.notes as notes,
    payload.auto_blocked as auto_blocked,

    _source_file,
    _ingested_at
from {{ ref('int_events_deduped') }}
where event_type = 'risk.alert'
