select * from {{ ref('int_auth_sessions') }}
where event_timestamp_quality = 'ok'
