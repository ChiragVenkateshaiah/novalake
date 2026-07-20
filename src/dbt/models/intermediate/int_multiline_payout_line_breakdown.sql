-- line_breakdown[] can be legitimately empty (choice([0,1,2]), never
-- missing) -- explode_outer preserves payouts with zero breakdown entries.
select
    t.event_id,
    t.page,
    breakdown_index,
    b.merchant_order,
    b.sub_items as sub_items  -- stays an array; exploded downstream
from {{ ref('int_multiline_payouts_clean') }} t
lateral view outer posexplode(t.line_breakdown) exploded_breakdown as breakdown_index, b
