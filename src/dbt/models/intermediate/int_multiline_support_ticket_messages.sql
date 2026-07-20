-- messages[] is guaranteed non-empty by construction (randint(1,5)) --
-- plain explode. reactions is a closed-enum dynamic map (only ever the
-- "agent" key, per data/generators/generate_multiline.py) -- direct
-- struct-field access, not MAP reconstruction, per the closed-enum
-- principle in docs/02-silver.md.
select
    t.event_id,
    t.ticket_id,
    message_index,
    m.sender,
    m.timestamp as message_timestamp,
    m.body_text,
    m.reactions.agent as reaction_agent,
    m.attachments as attachments  -- stays an array; exploded downstream
from {{ ref('int_multiline_support_tickets_clean') }} t
lateral view posexplode(t.messages) exploded_messages as message_index, m
