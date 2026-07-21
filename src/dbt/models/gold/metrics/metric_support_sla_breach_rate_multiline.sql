-- Grain: (event_date, priority). MULTILINE ONLY -- companion to
-- metric_support_resolution_time, not a substitute. sla_breached and
-- resolution_minutes measure structurally different things (a target/breach
-- flag vs. real elapsed time); there is no valid conversion between them.

select
    event_date,
    priority,
    count(*) as ticket_count,
    count(*) filter (where sla_breached = true) as breached_count,
    count(*) filter (where sla_breached = true) / nullif(count(*), 0) as sla_breach_rate
from {{ ref('fct_support_tickets') }}
where source = 'multiline'
group by event_date, priority
