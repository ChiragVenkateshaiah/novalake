select * from {{ ref('int_refunds') }}
where event_timestamp_quality != 'ok'
