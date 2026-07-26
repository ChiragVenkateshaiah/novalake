# Assistant notes

Personal reference notes, written by Claude for Chirag to revisit later —
not part of the formal `docs/NN-phase.md` doc set (see `docs/notes/README`-
style framing in `dab-dbt-explained.md` for the same spirit: mechanics and
"how do I actually see this" over decisions, which live in `docs/checkpoint.md`
and `docs/adr/`). Organized by topic, most recent topic first.

---

## v0.6 GenAI — where to look in the Databricks UI (2026-07-26)

A guided walkthrough of everything built in `v0.6`, in build order, with
exact names/IDs so you can find each artifact directly instead of hunting.
Cross-reference against `docs/06-genai.md` (what was decided and why) and
`docs/checkpoint.md` (the gated-action audit trail) if you want the full
story behind any of these.

### 1. Unity Catalog — the data/model layer

**Nav:** left sidebar → **Catalog** → `novalake` → `genai` schema

- The `genai` schema itself didn't exist before this session — it's new.
- **Models** tab → `support_assist_agent` → you should see **two
  versions** (v1, v2). Version 2 has the prompt-injection fix (Step 6.5);
  version 1 is kept only as a rollback target, not deleted.
- **Permissions** tab: should show just you as owner, no broader grants —
  that's what Step 6.6 confirmed live rather than assumed.

### 2. Vector Search — the RAG retrieval layer

**Nav:** left sidebar → **Compute** → **Vector Search** (or search
"Vector Search" in the top search bar)

- Endpoint: **`novalake-rag`** (Storage Optimized). Should read `ONLINE`.
- Click in → two indexes:
  - **`rag_support_ticket_index`** — "Indexed rows" should read **1255**
  - **`rag_review_index`** — "Indexed rows" should read **1034**
- These row counts matching their source tables
  (`novalake.gold.rag_support_ticket_corpus` / `rag_review_corpus`)
  exactly is the live-verification signal used throughout Step 6.3/6.4.

### 3. Model Serving — the two deployed endpoints

**Nav:** left sidebar → **Serving**

- **`novalake-support-assist`** — the RAG agent endpoint.
  - **Served entities** should show v1 and v2. Check **Traffic**: v2
    should be 100%, v1 should be 0%.
  - There's a **Review App** link here — try asking it something like
    *"A customer says a refund was approved but the money never arrived,
    what similar tickets have we seen?"* to see it live.
- **`mas-1b6eda83-endpoint`** — the text-to-SQL Supervisor Agent's
  endpoint. Agent Bricks tiles get an auto-generated endpoint name, not a
  friendly one — that's expected, not a naming bug.

### 4. Agent Bricks — the text-to-SQL surface

**Nav:** left sidebar → **Agents** (may be labeled **Agent Bricks**
depending on your workspace nav)

- Look for **`NovaLake Analytics Assistant`** — a Supervisor Agent (MAS)
  tile, `tile_id: 1b6eda83-e2d8-4cdb-8121-f8c51061fcaa`.
- Open it → one connected agent, **`gold_analytics`**, pointing at the
  existing **NovaLake Gold Analytics** Genie space
  (`space_id: 01f184ef1ae217509fe577597f00deb6`, built back at `v0.4` —
  just wrapped here, not rebuilt).
- Try asking it *"What was our approval rate in Q1 2026, across both
  sources?"* — worth trying **twice**, in separate conversations. That's
  the real, load-bearing finding from Step 6.8: certified-example SQL
  reuse in Genie is **non-deterministic** — the same literal question can
  reuse the correct pinned SQL on one attempt and free-generate a
  different query on another. Don't be alarmed if you see two different
  numbers; that's the documented behavior, not a new bug you found.
- Note: this tile has **no "Examples"** configured on purpose — Free
  Edition disables the embedding model that feature depends on
  (`MODEL_DISABLED`, confirmed via CLI, not an MCP-tool bug). Routing
  works correctly from `instructions` alone regardless (verified live in
  Step 6.7).

### 5. MLflow Experiments — the eval runs and model logging

**Nav:** left sidebar → **Experiments**

Look under `/Users/chiragvenkatesh92@gmail.com/novalake_genai_dev/` for
three experiments:
- **`support_assist_agent`** — the `mlflow.pyfunc.log_model` runs (where
  v1/v2 got logged before UC registration).
- **`support_assist_agent_eval`** — the RAG offline eval runs. Open the
  most recent run's **Traces** tab and click into a trace to see the
  actual tool calls and retrieved documents.
- **`sql_agent_eval`** — the SQL eval runs. Open a trace to see the exact
  SQL the Genie space generated for each question — this is how the
  non-determinism finding above was actually confirmed, not guessed.

### 6. Workspace files — the source code as Databricks sees it

**Nav:** left sidebar → **Workspace** → your user folder →
`novalake_genai_dev/genai/`

Mirrors `src/genai/` in the git repo (`agent.py`, `eval_agent.py`,
`eval_dataset.py`, `deploy_agent.py`, `sql_eval_dataset.py`, etc.). The
repo is the source of truth; this is just the uploaded copy the workspace
jobs actually ran.

### 7. Jobs — execution scaffolding, not a deliverable

**Nav:** left sidebar → **Workflows** → **Jobs**

Jobs named `novalake-genai-agent-*` and `novalake-genai-mas-eval` exist
only because `execute_code` doesn't work on this workspace this session —
every script had to run as a job instead of interactively. Not a
deliverable in themselves; safe to ignore, or delete if you want to tidy
up. Left in place in case you want to re-run an eval later without
re-uploading files.
