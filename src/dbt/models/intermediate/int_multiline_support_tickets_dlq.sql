select * from {{ ref('int_multiline_support_tickets') }}
where event_timestamp_quality != 'ok'
