select * from {{ ref('int_support_tickets') }}
where event_timestamp_quality != 'ok'
