-- Grain: (event_date, source). status = 'created' excluded -- in-flight, not
-- yet a completed/failed outcome.

select
    event_date,
    source,
    count(*) filter (where status = 'completed') as completed_count,
    count(*) filter (where status = 'failed') as failed_count,
    count(*) filter (where status = 'completed') / count(*) as approval_rate,
    count(*) filter (where status = 'failed') / count(*) as decline_rate
from {{ ref('fct_transactions') }}
where status in ('completed', 'failed')
group by event_date, source
