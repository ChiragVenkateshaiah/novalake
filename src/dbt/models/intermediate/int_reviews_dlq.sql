select * from {{ ref('int_reviews') }}
where event_timestamp_quality != 'ok'
