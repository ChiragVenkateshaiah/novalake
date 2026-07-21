-- Grain: (event_date, source, currency_clean). Native-currency, grouped by
-- currency -- never blended across currencies (no single blended total
-- exists without fx data, and NDJSON has none). See
-- metric_transaction_volume_usd_multiline for the companion USD-normalized
-- view, which is multiline-only.

select
    event_date,
    source,
    currency_clean,
    count(*) as transaction_count,
    count(*) filter (where status = 'completed') as completed_count,
    sum(amount_minor_resolved) / 100.0 as gross_amount_major
from {{ ref('fct_transactions') }}
group by event_date, source, currency_clean
