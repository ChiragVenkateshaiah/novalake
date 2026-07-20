-- tags[] can legitimately be empty (sample(k=randint(0,3)), never
-- maybe()-wrapped so never missing) -- explode_outer preserves tickets with
-- zero tags instead of silently dropping them.
select
    t.event_id,
    t.ticket_id,
    tag
from {{ ref('int_support_tickets_clean') }} t
lateral view outer explode(t.tags) exploded_tags as tag
