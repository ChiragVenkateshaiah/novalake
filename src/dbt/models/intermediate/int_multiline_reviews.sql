-- Scoped to review.submitted in the multiline file. Nested under
-- payload.review.* here, unlike the NDJSON file's flat payload.* --
-- confirmed against a real `describe`. media[]/replies[] arrays don't
-- exist in the NDJSON version at all -- exploded downstream off the clean
-- model.

select
    event_id,
    event_type,
    schema_version,
    page,
    resolved_event_timestamp,
    event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    customer_id_resolved,

    payload.review.merchant_id as merchant_id,
    payload.review.rating as rating,
    payload.review.title as title,
    payload.review.body as body,
    payload.review.media as media,
    payload.review.replies as replies,
    payload.verified_purchase as verified_purchase,

    _source_file,
    _ingested_at
from {{ ref('int_multiline_events_deduped') }}
where event_type = 'review.submitted'
