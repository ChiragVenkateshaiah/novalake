-- documents[] is guaranteed non-empty by construction (randint(1,3), never
-- maybe()-wrapped) -- plain explode, no explode_outer needed.
select
    t.event_id,
    t.event_type,
    t.resolved_event_timestamp,
    t.customer_id_resolved,
    doc_index,
    doc.doc_type,
    doc.verified,
    doc.uploaded_at
from {{ ref('int_kyc_verifications_clean') }} t
lateral view posexplode(t.documents) exploded_docs as doc_index, doc
