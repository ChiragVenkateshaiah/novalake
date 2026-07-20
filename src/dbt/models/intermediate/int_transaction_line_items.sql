-- Only explodes the CLEAN set (int_transactions_clean) -- DLQ rows stay at
-- transaction grain, unexploded, for easy review.
--
-- LATERAL VIEW OUTER posexplode, not inner explode/posexplode: line_items
-- has two independent edge cases -- a genuinely empty array (~1/7 of
-- transactions, n=0, a real business fact) and an independently missing
-- field (~5% via generate_events.py's maybe(items, 0.05, None), a real data
-- gap). A plain inner explode silently drops the parent row entirely in
-- both cases, which would delete ~18-19% of clean transactions from this
-- model with no trace. OUTER preserves exactly one row per transaction
-- (nulled-out item columns) in both cases instead.
select
    t.event_id,
    t.event_type,
    t.resolved_event_timestamp,
    t.customer_id_resolved,
    line_item_index,
    line_item.sku,
    line_item.qty,
    line_item.unit_price,
    line_item.tax_rate
from {{ ref('int_transactions_clean') }} t
lateral view outer posexplode(t.line_items) exploded_items as line_item_index, line_item
