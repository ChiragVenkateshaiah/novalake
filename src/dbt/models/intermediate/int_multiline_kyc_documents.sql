-- documents[] is guaranteed non-empty by construction (randint(1,3)) --
-- plain explode, no explode_outer needed.
select
    t.event_id,
    t.page,
    doc_index,
    doc.doc_type,
    doc.verified,
    doc.pages as pages  -- stays an array; exploded downstream
from {{ ref('int_multiline_kyc_verifications_clean') }} t
lateral view posexplode(t.documents) exploded_docs as doc_index, doc
