-- Scoped to auth.session in the multiline file. Same device
-- struct-vs-flat-fields reshaping as the NDJSON file's int_auth_sessions,
-- plus geo.coordinates (a fixed 2-element [lat, lon] pair -- left as an
-- array, not exploded) and device.sensors (v2-only dynamic-key map,
-- reconstructed as MAP for the same open-vocabulary reason as
-- transaction.metadata).

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

    payload.result as result,
    payload.mfa_used as mfa_used,

    payload.geo.country as geo_country_raw,
    {{ clean_country('payload.geo.country') }} as geo_country_clean,
    payload.geo.city as geo_city,
    payload.geo.coordinates as geo_coordinates,

    coalesce(payload.device.os, payload.device_os) as device_os_resolved,
    coalesce(payload.device.device_id, payload.device_id) as device_id_resolved,
    from_json(to_json(payload.device.sensors), 'map<string,string>') as device_sensors_map,

    _source_file,
    _ingested_at
from {{ ref('int_multiline_events_deduped') }}
where event_type = 'auth.session'
