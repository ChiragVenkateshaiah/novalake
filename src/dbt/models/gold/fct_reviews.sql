-- UNION ALL of both sources' review.submitted clean models. title/body free
-- text excluded (no current consumer -- same GenAI-deferral precedent as
-- ticket description). helpful_votes is ndjson-only (absent from
-- multiline's build_review).

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
        cast(null as int) as helpful_votes,   -- multiline's review payload has no helpful_votes field
        verified_purchase
    from {{ ref('int_multiline_reviews_clean') }}
)

select * from ndjson
union all
select * from multiline
