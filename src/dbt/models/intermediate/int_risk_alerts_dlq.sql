select * from {{ ref('int_risk_alerts') }}
where event_timestamp_quality != 'ok'
