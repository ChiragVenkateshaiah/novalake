-- UNION ALL of both sources' review.submitted clean models. helpful_votes is
-- ndjson-only (absent from multiline's build_review).
--
-- title/body un-excluded at v0.6 (was deferred per docs/checkpoint.md's "no
-- later-phase tooling early" principle -- same precedent as ticket
-- description) -- this is the second RAG corpus field for v0.6a's
-- support-assist index (docs/06-genai.md Step 6.1). No PII risk confirmed:
-- both generators (generate_events.py/generate_multiline.py) fill review
-- templates only with {merchant, os, cur} -- never a customer name/email.

with ndjson as (
    select
        concat('ndjson_', event_id) as review_key,
        event_id,
        'ndjson' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        merchant_id,
        rating,
        title,
        body,
        helpful_votes,
        verified_purchase
    from {{ ref('int_reviews_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as review_key,
        event_id,
        'multiline' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        merchant_id,
        rating,
        title,
        body,
        cast(null as int) as helpful_votes,   -- multiline's review payload has no helpful_votes field
        verified_purchase
    from {{ ref('int_multiline_reviews_clean') }}
)

select * from ndjson
union all
select * from multiline
