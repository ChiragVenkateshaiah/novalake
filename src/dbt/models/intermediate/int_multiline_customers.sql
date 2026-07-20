-- Cross-page dimension resolution: reference_data.customers is
-- independently regenerated per page (data/generators/generate_multiline.py's
-- customers_for_page(), no cross-page linkage field at all) -- a shared
-- customer_id across pages is two coincidentally shared identities drawn
-- from the same 10k-id pool, not one entity legitimately drifting (unlike
-- merchants' as_of_page). Union + dedupe with an arbitrary deterministic
-- tie-break; a resolved row may not match every page's version of that id,
-- and that's accepted as a property of this synthetic dataset, not a bug.

with exploded as (
    select
        pagination.page as page,
        customer.customer_id,
        customer.full_name,
        customer.addresses,
        customer.loyalty,
        customer.consents
    from {{ ref('stg_raw_events_multiline') }}
    lateral view explode(reference_data.customers) exploded_customers as customer
),

resolved as (
    select
        *,
        row_number() over (partition by customer_id order by customer_id) as rn
    from exploded
)

select
    customer_id,
    full_name,
    addresses,
    loyalty,
    consents
from resolved
where rn = 1
