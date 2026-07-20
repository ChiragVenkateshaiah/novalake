select * from {{ ref('int_payouts') }}
where event_timestamp_quality != 'ok'
