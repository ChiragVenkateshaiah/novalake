-- UNION ALL of both sources' support.ticket clean models. NDJSON has real
-- elapsed resolution_minutes; multiline only has an SLA target/breach flag
-- (sla.target_minutes/sla.breached) -- structurally non-equivalent concepts,
-- no conversion possible (confirmed field-by-field against both generators).
-- Kept as separate, source-scoped column pairs rather than forced into one
-- blended column -- see metric_support_resolution_time /
-- metric_support_sla_breach_rate_multiline for the same split at the metric
-- layer. related_transaction_id is a random UUID, never a real FK -- kept
-- informational, not FK-tested.

with ndjson as (
    select
        concat('ndjson_', event_id) as ticket_key,
        event_id,
        'ndjson' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        ticket_id,
        channel,
        priority,
        subject,
        related_transaction_id,
        resolved,
        resolution_minutes,
        cast(null as int) as sla_target_minutes,
        cast(null as boolean) as sla_breached
    from {{ ref('int_support_tickets_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as ticket_key,
        event_id,
        'multiline' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        ticket_id,
        channel,
        priority,
        subject,
        related_transaction_id,
        cast(null as boolean) as resolved,
        cast(null as int) as resolution_minutes,
        sla.target_minutes as sla_target_minutes,
        sla.breached as sla_breached
    from {{ ref('int_multiline_support_tickets_clean') }}
)

select * from ndjson
union all
select * from multiline
