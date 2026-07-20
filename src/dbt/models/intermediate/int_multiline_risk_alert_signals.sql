-- signals[] is guaranteed non-empty by construction (randint(1,4)) --
-- plain explode.
select
    t.event_id,
    t.page,
    signal_index,
    s.name as signal_name,
    s.weight as signal_weight,
    s.sub_signals as sub_signals  -- stays an array; exploded downstream
from {{ ref('int_multiline_risk_alerts_clean') }} t
lateral view posexplode(t.signals) exploded_signals as signal_index, s
