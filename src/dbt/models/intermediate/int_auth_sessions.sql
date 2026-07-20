-- Scoped to auth.session only. Payload-level drift resolution for this
-- event family: customer_id_resolved comes from the generic layer
-- (int_events_deduped); the device struct-vs-flat-fields reshaping below is
-- new and specific to this type -- nothing else shares this exact shape.

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

    payload.result as result,
    payload.mfa_used as mfa_used,

    payload.geo.country as geo_country_raw,
    {{ clean_country('payload.geo.country') }} as geo_country_clean,
    payload.geo.city as geo_city,

    -- Structural reshaping (v2 struct `device` vs v1 flat `device_os` +
    -- `device_id` fields) -- both shapes exist as nullable siblings in
    -- Bronze's inferred payload struct; exactly one is populated per row.
    coalesce(payload.device.os, payload.device_os) as device_os_resolved,
    coalesce(payload.device.device_id, payload.device_id) as device_id_resolved,

    _source_file,
    _ingested_at
from {{ ref('int_events_deduped') }}
where event_type = 'auth.session'
