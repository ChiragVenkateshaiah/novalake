-- sub_items[] is guaranteed non-empty by construction (randint(1,3)) --
-- plain explode. Keyed by (event_id, breakdown_index) since breakdown
-- entries have no stable id of their own.
select
    b.event_id,
    b.breakdown_index,
    sub_item_index,
    si.sku,
    si.net
from {{ ref('int_multiline_payout_line_breakdown') }} b
lateral view posexplode(b.sub_items) exploded_sub_items as sub_item_index, si
