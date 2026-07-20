-- replies[] can be legitimately empty (choice([0,0,1]), never missing) --
-- explode_outer preserves reviews with zero replies.
select
    t.event_id,
    t.page,
    reply_index,
    r.by as reply_by,
    r.text as reply_text,
    r.at as reply_at
from {{ ref('int_multiline_reviews_clean') }} t
lateral view outer posexplode(t.replies) exploded_replies as reply_index, r
