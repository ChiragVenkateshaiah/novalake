-- pages[] is guaranteed non-empty by construction (randint(1,3)) -- plain
-- explode. Keyed by (event_id, doc_index) since documents have no stable
-- id of their own.
select
    d.event_id,
    d.doc_index,
    page_index,
    p.page_no,
    p.ocr_conf
from {{ ref('int_multiline_kyc_documents') }} d
lateral view posexplode(d.pages) exploded_pages as page_index, p
