-- UNION ALL of both sources' auth.session clean models. geo_coordinates/
-- device_sensors_map (multiline-only fields) stay in the Silver model, not
-- duplicated here -- no named metric consumes them yet.

with ndjson as (
    select
        concat('ndjson_', event_id) as auth_session_key,
        event_id,
        'ndjson' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        result,
        mfa_used,
        geo_country_clean,
        geo_city,
        device_os_resolved,
        device_id_resolved
    from {{ ref('int_auth_sessions_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as auth_session_key,
        event_id,
        'multiline' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        result,
        mfa_used,
        geo_country_clean,
        geo_city,
        device_os_resolved,
        device_id_resolved
    from {{ ref('int_multiline_auth_sessions_clean') }}
)

select * from ndjson
union all
select * from multiline
