-- UNION ALL of both sources' transaction.{completed,failed,created} clean
-- models, one row per source event. Amounts stay NATIVE currency for both
-- sources (amount_minor_resolved + currency_clean) -- fx data only exists
-- for multiline (int_multiline_fx_rates, random-per-page, no real-world
-- grounding), so amount_minor_usd/fx_rate_quote_per_usd are multiline-only,
-- NULL for ndjson, never fabricated.
--
-- payment_method is flattened to 3 scalars on both sides -- multiline's
-- struct additionally carries network_tokens (not on NDJSON's), so a
-- whole-struct UNION would misalign/fail; only the 3 shared scalars are
-- safe to pass through.
--
-- NDJSON has no scalar merchant_id column -- it's reached via the ~2%-
-- nullable inline `merchant` struct (merchant.merchant_id). That struct's
-- name/category/country are a fresh random draw per event, not a stable
-- lookup (see dim_merchants) -- only merchant_id is used here as an FK.

with ndjson as (
    select
        concat('ndjson_', event_id) as transaction_key,
        event_id,
        'ndjson' as source,
        event_type,
        status,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        merchant.merchant_id as merchant_id,
        amount_minor_resolved,
        currency_clean,
        cast(null as double) as amount_minor_usd,
        cast(null as double) as fx_rate_quote_per_usd,
        country_clean,
        payment_method.type as payment_method_type,
        payment_method.brand as payment_method_brand,
        payment_method.last4 as payment_method_last4,
        risk_score,
        risk_flagged,
        risk_malformed,
        idempotency_key
    from {{ ref('int_transactions_clean') }}
),

multiline as (
    select
        concat('multiline_', event_id) as transaction_key,
        event_id,
        'multiline' as source,
        event_type,
        status,
        date(resolved_event_timestamp) as event_date,
        resolved_event_timestamp,
        customer_id_resolved as customer_id,
        merchant_id,
        amount_minor_resolved,
        currency_clean,
        amount_minor_usd,
        fx_rate_quote_per_usd,
        country_clean,
        payment_method.type as payment_method_type,
        payment_method.brand as payment_method_brand,
        payment_method.last4 as payment_method_last4,
        risk_score,
        risk_flagged,
        risk_malformed,
        idempotency_key
    from {{ ref('int_multiline_transactions_fx_applied') }}
)

select * from ndjson
union all
select * from multiline
