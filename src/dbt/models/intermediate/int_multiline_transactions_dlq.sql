select * from {{ ref('int_multiline_transactions') }}
where event_timestamp_quality != 'ok'
