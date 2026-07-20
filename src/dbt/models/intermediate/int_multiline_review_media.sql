-- media[] can be legitimately empty (choice([0,1]), never missing) --
-- explode_outer preserves reviews with zero media.
select
    t.event_id,
    t.page,
    media_index,
    m.type as media_type,
    m.url
from {{ ref('int_multiline_reviews_clean') }} t
lateral view outer posexplode(t.media) exploded_media as media_index, m
