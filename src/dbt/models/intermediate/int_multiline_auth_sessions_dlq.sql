select * from {{ ref('int_multiline_auth_sessions') }}
where event_timestamp_quality != 'ok'
