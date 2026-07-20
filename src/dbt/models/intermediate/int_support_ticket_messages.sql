-- messages[] is guaranteed non-empty by construction (randint(1,5), never
-- maybe()-wrapped) -- plain explode, no explode_outer needed.
select
    t.event_id,
    t.ticket_id,
    message_index,
    message.sender,
    message.timestamp as message_timestamp,
    message.body_text
from {{ ref('int_support_tickets_clean') }} t
lateral view posexplode(t.messages) exploded_messages as message_index, message
