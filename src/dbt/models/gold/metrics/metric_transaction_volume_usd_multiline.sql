-- Grain: event_date. MULTILINE ONLY -- fx data (and therefore a single
-- blended USD total) only exists for that source. Do not extend this to
-- ndjson: it has no fx rates to normalize with, and fabricating one would
-- misrepresent real data as normalized.

select
    event_date,
    sum(amount_minor_usd) / 100.0 as gross_amount_usd
from {{ ref('fct_transactions') }}
where source = 'multiline'
group by event_date
