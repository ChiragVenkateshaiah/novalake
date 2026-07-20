select * from {{ ref('int_multiline_risk_alerts') }}
where event_timestamp_quality != 'ok'
