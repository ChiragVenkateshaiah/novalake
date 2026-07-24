-- Vector Search's Delta Sync index requires a physical Delta table as its
-- source -- fct_support_tickets is a view (Gold's standard materialization,
-- overridden here per dbt_project.yml's `gold.genai` block), so this table
-- exists purely to give Vector Search something to sync from, not as a new
-- Gold fact. One row per ticket, matching fct_support_tickets' grain exactly.
--
-- `content` is the sole embedding_source_column (docs/06-genai.md Step
-- 6.2) -- description only, no chunking: every description is a single
-- short paragraph, well under even the smaller embedding model's context
-- window, so row-grain embedding is the whole document. subject/priority/
-- channel are carried as metadata for citation and filtering, not embedded.

select
    ticket_key,
    description as content,
    subject,
    priority,
    channel,
    source,
    event_date,
    customer_id
from {{ ref('fct_support_tickets') }}
