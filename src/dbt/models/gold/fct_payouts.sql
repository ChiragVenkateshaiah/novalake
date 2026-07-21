-- UNION ALL of both sources' payout.scheduled clean models. Merchant-centric
-- only -- no customer_id column at all (this event type has no customer key
-- in either generator). gross_amount stays a plain major-unit float on both
-- sides (no v1/v2 drift for this type). schedule is the one payload struct
-- confirmed identical in shape/enum values across both generators, safe to
-- flatten identically. payout_lead_days is a simple row-grain derivation off
-- two already-present timestamps, computed here (same precedent as Silver
-- computing risk_malformed inline).

with ndjson as (
    select
        concat('ndjson_', event_id) as payout_key,
        event_id,
        'ndjson' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        merchant_id,
        gross_amount,
        currency_clean,
        schedule.cycle as schedule_cycle,
        try_cast(schedule.scheduled_for as timestamp) as schedule_scheduled_for,
        schedule.status as schedule_status,
        bank_account_last4,
        datediff(try_cast(schedule.scheduled_for as timestamp), resolved_event_timestamp) as payout_lead_days
    from {{ ref('int_payouts_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as payout_key,
        event_id,
        'multiline' as source,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        merchant_id,
        gross_amount,
        currency_clean,
        schedule.cycle as schedule_cycle,
        try_cast(schedule.scheduled_for as timestamp) as schedule_scheduled_for,
        schedule.status as schedule_status,
        cast(null as string) as bank_account_last4,   -- multiline's payout payload has no bank_account_last4 field
        datediff(try_cast(schedule.scheduled_for as timestamp), resolved_event_timestamp) as payout_lead_days
    from {{ ref('int_multiline_payouts_clean') }}
)

select * from ndjson
union all
select * from multiline
