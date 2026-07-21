-- Grain: merchant_id. Rating-based rollups only -- no text-sentiment
-- scoring (deferred to v0.6 GenAI, per docs/checkpoint.md's "no
-- later-phase tooling early" principle).

select
    merchant_id,
    count(*) as rating_count,
    avg(rating) as avg_rating,
    count(*) filter (where rating = 1) as rating_1_count,
    count(*) filter (where rating = 2) as rating_2_count,
    count(*) filter (where rating = 3) as rating_3_count,
    count(*) filter (where rating = 4) as rating_4_count,
    count(*) filter (where rating = 5) as rating_5_count,
    count(*) filter (where verified_purchase = true) / nullif(count(*), 0) as verified_purchase_rate
from {{ ref('fct_reviews') }}
group by merchant_id
