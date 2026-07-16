-- Thin pass-through over Bronze: proves the dbt -> Unity Catalog read path works
-- end to end. Explode/flatten/drift-reconciliation is real Silver modeling work,
-- done in a later pass — not attempted here.

select
    event_id,
    event_type,
    schema_version,
    event_timestamp,
    ingested_at,
    source,
    source_system,
    payload,
    _source_file,
    _ingested_at
from {{ source('bronze', 'raw_events') }}
