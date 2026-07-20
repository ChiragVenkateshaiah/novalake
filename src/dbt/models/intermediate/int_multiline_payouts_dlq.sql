select * from {{ ref('int_multiline_payouts') }}
where event_timestamp_quality != 'ok'
