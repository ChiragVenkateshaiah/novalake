-- Cross-page dimension resolution: reference_data.merchants appears per
-- page, with ~40% of merchant_ids skipped on any given page and later
-- pages sometimes changing casing/category for the same merchant_id
-- (data/generators/generate_multiline.py's merchants_for_page()).
-- as_of_page is a real, principled ordering signal -- latest-wins.

with exploded as (
    select
        pagination.page as page,
        merchant.merchant_id,
        merchant.name,
        merchant.category,
        merchant.address,
        merchant.tax_ids,
        merchant.as_of_page
    from {{ ref('stg_raw_events_multiline') }}
    lateral view explode(reference_data.merchants) exploded_merchants as merchant
),

resolved as (
    select
        *,
        row_number() over (partition by merchant_id order by as_of_page desc) as rn
    from exploded
)

select
    merchant_id,
    name,
    category,
    address.country as country_raw,
    {{ clean_country('address.country') }} as country_clean,
    address.geo as geo,
    tax_ids,
    as_of_page
from resolved
where rn = 1
