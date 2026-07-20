-- fees[] can be legitimately empty (choice([0,1,2]), never missing) --
-- explode_outer preserves transactions with zero fees.
select
    t.event_id,
    t.page,
    fee_index,
    fee.kind as fee_kind,
    fee.amount as fee_amount
from {{ ref('int_multiline_transactions_clean') }} t
lateral view outer posexplode(t.fees) exploded_fees as fee_index, fee
