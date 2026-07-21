-- UNION ALL of both sources' kyc.verification clean models. Identical shape
-- on both sides at this grain (documents[] detail stays in the Silver child
-- explode models, not duplicated here).

with ndjson as (
    select
        concat('ndjson_', event_id) as kyc_verification_key,
        event_id,
        'ndjson' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        full_name,
        status,
        risk_score
    from {{ ref('int_kyc_verifications_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as kyc_verification_key,
        event_id,
        'multiline' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        full_name,
        status,
        risk_score
    from {{ ref('int_multiline_kyc_verifications_clean') }}
)

select * from ndjson
union all
select * from multiline
