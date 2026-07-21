-- UNION ALL of both sources' risk.alert clean models. Identical shape on
-- both sides at this grain (signals[] detail stays in the Silver child
-- explode models, not duplicated here).

with ndjson as (
    select
        concat('ndjson_', event_id) as risk_alert_key,
        event_id,
        'ndjson' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        alert_type,
        severity,
        notes,
        auto_blocked
    from {{ ref('int_risk_alerts_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as risk_alert_key,
        event_id,
        'multiline' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        alert_type,
        severity,
        notes,
        auto_blocked
    from {{ ref('int_multiline_risk_alerts_clean') }}
)

select * from ndjson
union all
select * from multiline
