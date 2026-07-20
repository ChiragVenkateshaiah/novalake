-- Parses the `raw` stringified JSON blob (already isolated in Increment 4)
-- against the broken event's own fixed, minimal shape -- confirmed against
-- data/generators/generate_multiline.py's partial_failures():
-- {"event_id": ..., "event_type": "transaction.completed",
--  "payload": {"transaction": {"amount": "NaN", "currency": null}}}.
-- Stays its own quarantine table -- never joined into the clean event
-- pipeline (int_multiline_events / int_multiline_transactions etc.).
select
    page,
    failure_index,
    failure_id,
    stage,
    error_code,
    attempted_at,
    retryable,
    from_json(
        raw,
        'event_id string, event_type string, payload struct<transaction:struct<amount:string, currency:string>>'
    ) as raw_parsed
from {{ ref('int_multiline_partial_failures') }}
