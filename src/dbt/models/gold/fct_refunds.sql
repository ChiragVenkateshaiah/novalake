-- UNION ALL of both sources' refund.issued clean models. amount stays a
-- plain major-unit float on both sides (no v1/v2 minor-unit drift exists for
-- this event type, confirmed against both generators -- unlike
-- transaction.*). original_transaction_id is a random UUID, never a real FK
-- into any transaction's event_id -- informational only, not FK-tested.

with ndjson as (
    select
        concat('ndjson_', event_id) as refund_key,
        event_id,
        'ndjson' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        original_transaction_id,
        amount,
        currency_clean,
        reason,
        partial,
        notes
    from {{ ref('int_refunds_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as refund_key,
        event_id,
        'multiline' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        original_transaction_id,
        amount,
        currency_clean,
        reason,
        partial,
        cast(null as string) as notes   -- multiline's refund payload has no notes field
    from {{ ref('int_multiline_refunds_clean') }}
)

select * from ndjson
union all
select * from multiline
