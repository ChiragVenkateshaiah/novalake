-- fees[] can legitimately be empty (choice([0,1,2,3]), never maybe()-wrapped
-- so never missing) -- explode_outer preserves payouts with zero fees
-- instead of silently dropping them.
select
    t.event_id,
    t.event_type,
    t.resolved_event_timestamp,
    t.merchant_id,
    fee_index,
    fee.type as fee_type,
    fee.amount as fee_amount
from {{ ref('int_payouts_clean') }} t
lateral view outer posexplode(t.fees) exploded_fees as fee_index, fee
