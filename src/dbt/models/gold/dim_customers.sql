-- Conformed across both sources: customer_id is drawn from the same
-- cust_10000-19999 pool by both generators (confirmed in
-- data/generators/generate_events.py and generate_multiline.py), so a shared
-- identity is real, not assumed. Built from every _clean model that carries a
-- real customer_id (7 event families x 2 sources -- payout.scheduled has none,
-- excluded), not from Gold facts, to keep dimensions ahead of facts in the DAG.
--
-- Deliberately sparse: int_multiline_customers only samples 40-70 customers
-- per page out of the full pool (customers_for_page() in generate_multiline.py),
-- so most rows here will have NULL profile columns -- has_multiline_profile
-- makes that explicit rather than leaving it implicit.

with customer_ids as (
    select customer_id_resolved as customer_id from {{ ref('int_transactions_clean') }}
    union
    select customer_id_resolved from {{ ref('int_refunds_clean') }}
    union
    select customer_id_resolved from {{ ref('int_auth_sessions_clean') }}
    union
    select customer_id_resolved from {{ ref('int_kyc_verifications_clean') }}
    union
    select customer_id_resolved from {{ ref('int_support_tickets_clean') }}
    union
    select customer_id_resolved from {{ ref('int_reviews_clean') }}
    union
    select customer_id_resolved from {{ ref('int_risk_alerts_clean') }}
    union
    select customer_id_resolved from {{ ref('int_multiline_transactions_clean') }}
    union
    select customer_id_resolved from {{ ref('int_multiline_refunds_clean') }}
    union
    select customer_id_resolved from {{ ref('int_multiline_auth_sessions_clean') }}
    union
    select customer_id_resolved from {{ ref('int_multiline_kyc_verifications_clean') }}
    union
    select customer_id_resolved from {{ ref('int_multiline_support_tickets_clean') }}
    union
    select customer_id_resolved from {{ ref('int_multiline_reviews_clean') }}
    union
    select customer_id_resolved from {{ ref('int_multiline_risk_alerts_clean') }}
)

select
    c.customer_id,
    p.full_name,
    p.addresses,
    p.loyalty,
    p.consents,
    p.full_name is not null as has_multiline_profile
from customer_ids c
left join {{ ref('int_multiline_customers') }} p
    on c.customer_id = p.customer_id
where c.customer_id is not null
