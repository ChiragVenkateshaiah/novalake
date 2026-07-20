-- discounts[] can be legitimately empty (choice([0,0,1,2]), never missing --
-- discounts() always returns a list) -- explode_outer preserves line items
-- with zero discounts. Keyed by (event_id, line_item_index) since line
-- items have no stable id of their own.
select
    li.event_id,
    li.line_item_index,
    discount_index,
    discount.code,
    discount.type as discount_type,
    discount.value as discount_value
from {{ ref('int_multiline_line_items') }} li
lateral view outer posexplode(li.discounts) exploded_discounts as discount_index, discount
