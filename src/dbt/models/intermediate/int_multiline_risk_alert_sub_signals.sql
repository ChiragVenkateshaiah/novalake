-- sub_signals[] can be legitimately empty (randint(0,2), never missing) --
-- explode_outer preserves signals with zero sub-signals. Keyed by
-- (event_id, signal_index) since signals have no stable id of their own.
select
    sg.event_id,
    sg.signal_index,
    sub_signal_index,
    ss.k,
    ss.v
from {{ ref('int_multiline_risk_alert_signals') }} sg
lateral view outer posexplode(sg.sub_signals) exploded_sub_signals as sub_signal_index, ss
