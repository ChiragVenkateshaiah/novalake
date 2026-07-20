-- line_items can be legitimately missing (maybe(...,0.05)) or empty
-- (choice([0,1,1,2,3,4])) -- explode_outer preserves both cases instead of
-- silently dropping the parent transaction.
-- attributes (per-item dynamic-key map, same dyn_metadata() shape as
-- transaction-level metadata) reconstructed as MAP for the same
-- open-vocabulary reason.
select
    t.event_id,
    t.page,
    line_item_index,
    line_item.sku,
    line_item.qty,
    line_item.unit_price,
    line_item.tax_rate,
    from_json(to_json(line_item.attributes), 'map<string,string>') as attributes_map,
    line_item.discounts as discounts  -- stays an array; exploded downstream
from {{ ref('int_multiline_transactions_clean') }} t
lateral view outer posexplode(t.line_items) exploded_line_items as line_item_index, line_item
