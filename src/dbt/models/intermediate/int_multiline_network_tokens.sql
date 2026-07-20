-- payment_method.network_tokens[] can be legitimately empty
-- (choice([0,1,2]), never missing) -- explode_outer preserves transactions
-- with zero tokens.
select
    t.event_id,
    t.page,
    token_index,
    token.token,
    token.expires
from {{ ref('int_multiline_transactions_clean') }} t
lateral view outer posexplode(t.payment_method.network_tokens) exploded_tokens as token_index, token
