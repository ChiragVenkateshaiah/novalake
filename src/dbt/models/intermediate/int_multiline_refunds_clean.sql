select * from {{ ref('int_multiline_refunds') }}
where event_timestamp_quality = 'ok'
