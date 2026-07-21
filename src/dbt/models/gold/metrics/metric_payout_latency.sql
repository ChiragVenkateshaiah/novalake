-- Grain: (event_date, source, schedule_status). payout_lead_days computed
-- at fct_payouts grain (datediff(schedule_scheduled_for, resolved_event_timestamp)).

select
    event_date,
    source,
    schedule_status,
    count(*) as payout_count,
    avg(payout_lead_days) as avg_lead_days,
    percentile_approx(payout_lead_days, 0.5) as p50_lead_days,
    percentile_approx(payout_lead_days, 0.9) as p90_lead_days
from {{ ref('fct_payouts') }}
group by event_date, source, schedule_status
