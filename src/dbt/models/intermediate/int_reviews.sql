-- Scoped to review.submitted only. No payload drift beyond
-- customer_id_resolved (from the generic layer) -- every other field is
-- stable across v1/v2.

select
    event_id,
    event_type,
    schema_version,
    resolved_event_timestamp,
    event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    resolved_source_host,
    customer_id_resolved,

    payload.merchant_id as merchant_id,
    payload.rating as rating,
    payload.title as title,
    payload.body as body,
    payload.helpful_votes as helpful_votes,
    payload.verified_purchase as verified_purchase,

    _source_file,
    _ingested_at
from {{ ref('int_events_deduped') }}
where event_type = 'review.submitted'
