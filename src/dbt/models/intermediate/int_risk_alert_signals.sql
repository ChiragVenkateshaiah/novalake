-- signals[] is guaranteed non-empty by construction (randint(1,4), never
-- maybe()-wrapped) -- plain explode, no explode_outer needed.
select
    t.event_id,
    t.event_type,
    t.resolved_event_timestamp,
    t.customer_id_resolved,
    signal_index,
    signal.name as signal_name,
    signal.weight as signal_weight,
    signal.value as signal_value
from {{ ref('int_risk_alerts_clean') }} t
lateral view posexplode(t.signals) exploded_signals as signal_index, signal
