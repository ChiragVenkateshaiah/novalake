-- Same reasoning as rag_support_ticket_corpus.sql: a physical Delta table
-- Vector Search can sync from, since fct_reviews is a view. One row per
-- review, matching fct_reviews' grain exactly.
--
-- `content` concatenates title + body into one embeddable field (docs/06-
-- genai.md Step 6.2) -- title alone ("Refund took forever") often carries
-- topic/sentiment signal not fully repeated in body, so folding both into
-- one field gives the embedding model the complete document instead of
-- picking one over the other. No chunking: combined title+body is still a
-- single short paragraph. Raw title/body kept as separate columns too, for
-- citation/display without re-splitting content.

select
    review_key,
    concat(title, '. ', body) as content,
    title,
    body,
    rating,
    source,
    event_date,
    customer_id,
    merchant_id
from {{ ref('fct_reviews') }}
