-- Conformed across both sources: merchant_id is drawn from the same
-- mer_1000-1099 pool by both generators. Built from the 6 _clean models that
-- carry a real merchant_id FK (support.ticket only has a merchant NAME in
-- free text, no FK -- excluded). NDJSON's transaction.merchant struct
-- (name/category/country) is a fresh random draw per occurrence, not a
-- stable lookup (merchant_struct() in generate_events.py) -- only its
-- merchant_id is used here as a foreign key; int_multiline_merchants
-- (genuine cross-page, latest-wins reference data) is the sole attribute
-- source of truth.
--
-- Written with the same defensive LEFT JOIN pattern as dim_customers even
-- though multiline's reference data already covers the full 100-merchant
-- range in this dataset (Silver's own validated int_multiline_merchants row
-- count = 100) -- that completeness is a property of this dataset, not
-- something to assume structurally.

with merchant_ids as (
    select merchant.merchant_id as merchant_id from {{ ref('int_transactions_clean') }}
    union
    select merchant_id from {{ ref('int_reviews_clean') }}
    union
    select merchant_id from {{ ref('int_payouts_clean') }}
    union
    select merchant_id from {{ ref('int_multiline_transactions_clean') }}
    union
    select merchant_id from {{ ref('int_multiline_reviews_clean') }}
    union
    select merchant_id from {{ ref('int_multiline_payouts_clean') }}
)

select
    m.merchant_id,
    p.name,
    p.category,
    p.country_clean,
    p.geo,
    p.tax_ids,
    p.name is not null as has_multiline_profile
from merchant_ids m
left join {{ ref('int_multiline_merchants') }} p
    on m.merchant_id = p.merchant_id
where m.merchant_id is not null
