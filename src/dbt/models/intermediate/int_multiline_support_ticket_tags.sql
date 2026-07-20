-- tags[] can be legitimately empty (sample(k=randint(0,3)), never missing)
-- -- explode_outer preserves tickets with zero tags.
select
    t.event_id,
    t.ticket_id,
    tag
from {{ ref('int_multiline_support_tickets_clean') }} t
lateral view outer explode(t.tags) exploded_tags as tag
