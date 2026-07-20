-- fx_rates are already page/as_of-scoped -- no cross-page conflict to
-- resolve, just a union across pages. `as_of` is NOT usable as a real
-- "rate in effect at transaction time" key -- verified against
-- fx_rates_for_page(): it's an independently random timestamp with no
-- causal relationship to any transaction on that page. (page, quote) is
-- the only real join key, used downstream in
-- int_multiline_transactions_fx_applied.sql. USD (the base currency) never
-- gets its own rate row here by generator design -- that model's LEFT JOIN
-- + coalesce(rate, 1.0) handles it, not this one.
select
    pagination.page as page,
    fx.base,
    fx.quote,
    fx.rate,
    fx.as_of
from {{ ref('stg_raw_events_multiline') }}
lateral view explode(reference_data.fx_rates) exploded_fx as fx
