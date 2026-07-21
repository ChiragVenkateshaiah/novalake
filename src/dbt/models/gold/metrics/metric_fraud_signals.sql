-- Grain: (event_date, source). Two independent, NOT blended measures -- no
-- FK links risk.alert events to specific transactions in this dataset
-- (confirmed: no transaction_id field in build_risk_alert in either
-- generator), so a single "fraud rate" spanning both fact tables would be
-- fabricated, not derived.
--
-- txn_risk_flagged_rate's denominator is deliberately count(*) (every
-- transaction), not a count that excludes the ~3% risk_malformed rows.
-- risk_flagged is NULL (not false) for those rows -- counting them out of
-- the denominator would inflate the rate by shrinking it based on a data-
-- quality issue, not a business signal. They're counted as "not flagged"
-- in the numerator (NULL doesn't match = true) and included in the
-- denominator -- a deliberate choice, not avg()'s silent NULL-drop default.

with txn_risk as (
    select
        event_date,
        source,
        count(*) as transaction_count,
        count(*) filter (where risk_flagged = true) as risk_flagged_count
    from {{ ref('fct_transactions') }}
    group by event_date, source
),

alert_risk as (
    select
        event_date,
        source,
        count(*) as alert_count,
        count(*) filter (where auto_blocked = true) as auto_blocked_count
    from {{ ref('fct_risk_alerts') }}
    group by event_date, source
)

select
    coalesce(t.event_date, a.event_date) as event_date,
    coalesce(t.source, a.source) as source,
    t.transaction_count,
    t.risk_flagged_count,
    t.risk_flagged_count / nullif(t.transaction_count, 0) as txn_risk_flagged_rate,
    a.alert_count,
    a.auto_blocked_count,
    a.auto_blocked_count / nullif(a.alert_count, 0) as alert_auto_block_rate
from txn_risk t
full outer join alert_risk a
    on t.event_date = a.event_date and t.source = a.source
