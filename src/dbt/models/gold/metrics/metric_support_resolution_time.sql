-- Grain: (event_date, priority). NDJSON ONLY -- resolution_minutes is real
-- elapsed time, a concept multiline's payload doesn't carry at all (it only
-- has an SLA target/breach flag). See metric_support_sla_breach_rate_multiline
-- for the companion multiline-only metric -- deliberately not blended into
-- one number, per the project owner's decision.

select
    event_date,
    priority,
    count(*) filter (where resolved = true) as resolved_count,
    avg(resolution_minutes) filter (where resolved = true) as avg_resolution_minutes
from {{ ref('fct_support_tickets') }}
where source = 'ndjson'
group by event_date, priority
