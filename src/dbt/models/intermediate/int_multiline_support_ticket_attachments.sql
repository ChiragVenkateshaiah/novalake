-- attachments[] can be legitimately empty (choice([0,0,1,2]), never
-- missing) -- explode_outer preserves messages with zero attachments.
-- Keyed by (event_id, message_index) since messages have no stable id of
-- their own.
select
    m.event_id,
    m.message_index,
    attachment_index,
    a.file,
    a.size_kb
from {{ ref('int_multiline_support_ticket_messages') }} m
lateral view outer posexplode(m.attachments) exploded_attachments as attachment_index, a
