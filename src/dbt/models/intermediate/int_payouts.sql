-- Scoped to payout.scheduled only. No customer_id_resolved -- this event
-- type is merchant-centric, has no customer key at all (verified against
-- data/generators/generate_events.py's build_payout -- resolves to NULL
-- for these rows in int_events_deduped's generic coalesce, by design).
-- `schedule` struct passed through as-is (no drift). fees[] stays an array
-- here; exploded downstream off the clean model (int_payout_fees.sql) --
-- can legitimately be empty (choice([0,1,2,3])), so that explode uses
-- explode_outer.

select
    event_id,
    event_type,
    schema_version,
    resolved_event_timestamp,
    event_timestamp_quality,
    resolved_source_system,
    resolved_source_region,
    resolved_source_host,

    payload.merchant_id as merchant_id,
    payload.gross_amount as gross_amount,
    payload.currency as currency_raw,
    {{ clean_currency('payload.currency') }} as currency_clean,
    payload.schedule as schedule,
    payload.fees as fees,
    payload.bank_account_last4 as bank_account_last4,

    _source_file,
    _ingested_at
from {{ ref('int_events_deduped') }}
where event_type = 'payout.scheduled'
