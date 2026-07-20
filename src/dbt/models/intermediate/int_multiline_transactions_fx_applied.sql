-- Normalizes amount_minor_resolved to a common USD base using the embedded
-- fx_rates. LEFT JOIN + coalesce(rate, 1.0) is required, not optional: the
-- generator never emits a USD rate row (fx_rates_for_page() explicitly
-- skips its own base currency), so an inner join would silently drop or
-- null every USD transaction's normalized amount.
--
-- Rate semantics verified against fx_rates_for_page(): {"base": "USD",
-- "quote": q, "rate": ...} means 1 USD = `rate` units of `quote` -- so
-- converting FROM quote TO USD divides by rate, not multiplies.
select
    t.*,
    fx.rate as fx_rate_quote_per_usd,
    round(t.amount_minor_resolved / coalesce(fx.rate, 1.0)) as amount_minor_usd
from {{ ref('int_multiline_transactions_clean') }} t
left join {{ ref('int_multiline_fx_rates') }} fx
    on t.page = fx.page
    and t.currency_clean = fx.quote
