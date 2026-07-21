-- Grain: (event_date, source). An aggregate ratio, not a join --
-- original_transaction_id is a random UUID in this synthetic dataset, never
-- a real FK into a transaction's event_id, so refund_count and
-- completed_transaction_count are computed independently and only combined
-- at the (event_date, source) grain.

with refunds as (
    select event_date, source, count(*) as refund_count
    from {{ ref('fct_refunds') }}
    group by event_date, source
),

completed_transactions as (
    select event_date, source, count(*) as completed_transaction_count
    from {{ ref('fct_transactions') }}
    where status = 'completed'
    group by event_date, source
)

select
    coalesce(r.event_date, t.event_date) as event_date,
    coalesce(r.source, t.source) as source,
    coalesce(r.refund_count, 0) as refund_count,
    coalesce(t.completed_transaction_count, 0) as completed_transaction_count,
    coalesce(r.refund_count, 0) / nullif(t.completed_transaction_count, 0) as refund_rate
from refunds r
full outer join completed_transactions t
    on r.event_date = t.event_date and r.source = t.source
