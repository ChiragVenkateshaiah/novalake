select * from {{ ref('int_multiline_reviews') }}
where event_timestamp_quality = 'ok'
