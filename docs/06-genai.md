# Module 6 · GenAI

`Status:` Draft — scoping only, build not started  ·  `Owner:` Chirag  ·
`Last updated:` v0.6 (scoping, 2026-07-24)  ·  `Est. time:` ___

**Sequencing decision (recorded here, not in a separate ADR — this is a
scope/sequencing call for this one module, not standing architecture):** RAG
(support-assist, Vector Search) is built and shipped before text-to-SQL
(Agent Bricks over the existing Genie space), within this **one** `v0.6` —
not split into two phases/tags, since `v0.7` is already claimed by
Declarative Pipelines. §6 below is organized as two step-groups reflecting
this: A (RAG, §6.1–6.6) then B (text-to-SQL, §6.7–6.9), explicitly
sequenced. See [ADR-0009](adr/0009-agentic-integration-mcp-gated-review-then-act.md)
for the separate (and standing, project-wide) decision this module also
depends on: from `v0.6` onward, Claude may invoke Databricks MCP actions
directly, gated by per-action review — see `CLAUDE.md`'s operational summary
of that gate before running any step below.

## 1. Learning Objectives
- [ ] Can decide what free text is safe to embed into a retrievable index and
      what needs masking first, before building the index — not as an
      afterthought once retrieval already works
- [ ] Can carry forward serving-layer guardrails (established at `v0.4`'s
      Genie space) into a new consumer surface deliberately, instead of
      re-deriving them from scratch or silently dropping them
- [ ] Can evaluate a RAG/text-to-SQL system against an offline eval set with
      groundedness and correctness scorers, not just "it looks right" spot
      checks
- [ ] Can operate under a review-then-act agentic workflow — proposing a live
      workspace action with full parameters and waiting for explicit
      go-ahead, rather than either asking permission vaguely or acting
      unilaterally

## 2. Prerequisites
- Completed modules: `v0.4` Serving (Genie space + dashboard on Gold, tagged
  `v0.4`; see `docs/04-serving.md`), `v0.5` CI/CD (tagged `v0.5`; see
  `docs/05-cicd.md`)
- Tables / assets that must already exist: the 20 Gold models (see
  `docs/03-gold.md`), the "NovaLake Gold Analytics" Genie space and its
  documented spec (`docs/serving/genie_space.md`,
  `docs/serving/question_catalog.md`)
- Compute / cluster config: unchanged from Serving — Serverless SQL
  warehouse; Vector Search and Agent Bricks compute requirements to be
  confirmed against Free Edition availability/quota before the first live
  resource is created (see ADR-0009 Consequences)
- New prerequisite specific to this module: [ADR-0009](adr/0009-agentic-integration-mcp-gated-review-then-act.md)
  decided (agentic MCP-gated review-then-act access) and `CLAUDE.md`
  drafted, both landing via this module's own scoping PR before any RAG/
  Agent Bricks build work starts

## 3. Where This Fits (Architecture Context)
- One-line: consumes the same Gold layer Serving does (plus a small amount
  of Gold-corpus work named in §5), and adds two new consumer surfaces on
  top — a support-assist RAG chat and a text-to-SQL agent — without
  replacing the existing Genie space/dashboard
- Reference diagram: `README.md` → Architecture (mermaid) already shows the
  GenAI layer as the terminal node consuming Serving's output; `docs/architecture.md`
- Inputs → this module → Outputs: `novalake.gold.*` (plus new/extended text
  fields — see §5) → RAG index + Agent Bricks agents → a support-assist chat
  surface and a text-to-SQL surface, both inheriting the guardrails Genie's
  serving layer already established (`docs/serving/genie_space.md`)

## 4. Concepts & Background
- Embeddings & chunking strategy — filled at build time
- Vector Search endpoint vs. index — filled at build time; see the
  `databricks-vector-search` skill
- Agent Bricks: tools, memory, orchestration (Knowledge Assistant vs.
  supervisor patterns) — filled at build time; see the
  `databricks-agent-bricks` skill
- Groundedness vs. correctness evaluation — filled at build time; see the
  `databricks-mlflow-evaluation` skill (built-in scorers: `Guidelines`,
  `Correctness`, `Safety`, `RetrievalGroundedness`)
- Common pitfalls / gotchas to watch for: a capable text-to-SQL model can
  find and misuse a technically-valid-looking join that a human wouldn't —
  this is *why* `original_transaction_id`/`related_transaction_id` were
  excluded from the Genie space's column visibility rather than merely
  instructed against (`docs/serving/genie_space.md`); the same reasoning
  applies to whatever surface Step-group B builds

## 5. Data Contract / Schema in Scope

**RAG corpus — named explicitly, not yet fully in Gold:**
- `fct_support_tickets.subject` — already Gold.
- `fct_support_tickets.description` / `messages[]` — **Silver-only today.**
  `int_support_tickets.sql` carries a standing comment: *"description is
  free text — kept as-is, this is the field the eventual GenAI layer will
  index, not something to 'clean'."* The `messages` array is exploded at
  Silver (`int_support_ticket_messages.sql`, grain `event_id` +
  `message_index`); the exact subfield holding message text needs
  build-time confirmation. Decide at build time whether this needs a new
  Gold model (e.g. `fct_support_ticket_messages`) or an extended
  `fct_support_tickets`.
- `fct_reviews.title` / `body` — **excluded from Gold today**
  (`fct_reviews.sql`: "title/body free text excluded ... same GenAI-deferral
  precedent as ticket description"). Decide whether to un-exclude — a
  code-comment reversal, not an ADR supersession.
- `fct_refunds.reason`/`notes`, `fct_risk_alerts.notes` — candidates, not yet
  decided in/out. Don't silently include everything; name each field's
  status explicitly before it's indexed.

**PII / sensitive-data policy — a scoping decision, recorded here, not a
build-time afterthought.** Structured Gold facts were safe to serve because
they're IDs/numbers; the free-text fields above are exactly where customer
names, emails, and free-text transaction references live. Embedding raw
free text into a Vector Search index that a chat agent can retrieve and
surface verbatim creates a PII-retrieval surface that doesn't exist today.
**Decision to make before the first field above is embedded:** whether to
mask/redact (`ai_mask`, UC classification tagging) before indexing — this
may change the Gold model shape itself (e.g. a `description_redacted`
column vs. raw `description`). Record the decision here once made; see §8
for the governance framing.

- Target schema (produced): not yet defined — depends on the embedding/
  index-shape decision in §6.2
- Schema-evolution policy: not applicable yet
- Keys / grain / uniqueness: not applicable yet

## 6. Step-by-Step Implementation

**Step-group A — RAG / support-assist (build before Step-group B):**

- **Step 6.1 — RAG corpus decision**
  - *Objective:* finalize which Gold/Silver text fields form the corpus (see
    §5) and whether new Gold models are needed
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___
- **Step 6.2 — Embedding + chunking strategy**
  - *Objective:* decide one Vector Search endpoint, one index per corpus
    source vs. one combined index with a `source_table` metadata column;
    defer embedding model/dimension choice to this step
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___
- **Step 6.3 — Vector Search endpoint + index creation**
  - *Objective:* first live resource this module creates — start narrow
    per ADR-0009, one index end-to-end before anything else
  - *Task:* MCP-gated action per ADR-0009/`CLAUDE.md` — full parameter set
    presented and approved before creation; check Free Edition availability/
    quota/billing directly first
  - *Expected output:* `resources/vector_search.yml` if DAB supports the
    resource type (check via `databricks-bundles` skill — not resolved by
    scoping), or a documented MCP-created resource if not
  - *Validation check:* ___
- **Step 6.4 — RAG agent**
  - *Objective:* retrieval + generation, likely an Agent Bricks Knowledge
    Assistant
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___
- **Step 6.5 — Offline eval set + groundedness/correctness scorers**
  - *Objective:* seed from `docs/serving/question_catalog.md`'s existing
    certified pairs plus new support-assist questions; score with MLflow's
    `Guidelines`/`Correctness`/`Safety`/`RetrievalGroundedness`
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___
- **Step 6.6 — Serving surface + access control**
  - *Objective:* ___
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___
- **[Recommended] Tag `v0.6.0-rag`** at the end of Step-group A, before
  Step-group B starts — `main` would otherwise carry a working,
  live-resource-backed RAG deployment with no rollback marker between the
  two sub-phases; `v0.5` (pre-RAG) would be the only fallback otherwise.
  Confirm this step-group independently meets DoD-for-its-scope (this doc's
  §1–9 filled for Step-group A, validation green) at that point even though
  the full `v0.6` tag waits for Step-group B.

**Step-group B — text-to-SQL (explicitly after Step-group A):**

- **Step 6.7 — Agent Bricks surface over the existing Genie space**
  - *Objective:* decide whether Agent Bricks wraps/supervises the existing
    "NovaLake Gold Analytics" Genie space directly, or re-declares a
    from-scratch text-to-SQL agent — either way, carry forward every
    guardrail in `docs/serving/genie_space.md`/`question_catalog.md`
    explicitly, especially the excluded-UUID-columns precedent (quoted in
    §4 above, not paraphrased)
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___
- **Step 6.8 — Offline eval set for SQL correctness**
  - *Objective:* reuse `question_catalog.md`'s 6 certified question→SQL
    pairs directly as a starting set, extended with new text-to-SQL-specific
    cases, scored on execution/result correctness
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___
- **Step 6.9 — Serving surface + access control**
  - *Objective:* ___
  - *Task:* ___
  - *Expected output:* ___
  - *Validation check:* ___

## 7. Operational Considerations
- Idempotency / re-run safety: ___
- Incremental vs full refresh: ___ (how the index stays in sync with Gold
  as new events land — a decision Step 6.2/6.3 need to make explicit)
- Performance (partitioning / clustering / file sizing): not applicable to
  the RAG index in the traditional sense; index sizing/sync mode is a
  parameter Step 6.3's MCP-gated creation must surface for approval
- Failure & retry behaviour: ___

## 8. Data Quality & Governance
- Expectations / rules applied: the 4 adversarial-misuse guardrails from
  `docs/serving/genie_space.md` (fx-blending, support-metric-blending,
  no-UUID-joins, rate-averaging), carried forward per §4/§6.7 — see
  `CLAUDE.md`'s "Known data guardrails" section for the standing copy
- **PII/redaction policy for the RAG corpus:** decision pending — see §5.
  Record the final decision here once made, before Step 6.3 embeds anything.
- Quarantine / reject handling: ___
- Lineage & catalog tags: ___
- Ownership & access: MCP-gated actions per ADR-0009 govern who/what can
  create or modify the live Vector Search/Agent Bricks resources this
  module introduces; every executed action is logged to
  `docs/checkpoint.md`'s revisit-log (see ADR-0009 §3)

## 9. Validation & Acceptance Criteria
- [ ] RAG corpus + PII policy decided and recorded (§5)
- [ ] Vector Search index live, queryable, results grounded per eval (§6.5)
- [ ] Text-to-SQL surface live, inheriting Genie's guardrails, correctness
      eval passing (§6.8)
- [ ] Sign-off: ___

## 10. Key Takeaways
- ___

## 11. Knowledge Check
- Q1: ___

## 12. References
- Internal: `docs/checkpoint.md` (the `v0.6` re-open decision this module
  depends on), [ADR-0009](adr/0009-agentic-integration-mcp-gated-review-then-act.md),
  `docs/serving/genie_space.md` + `docs/serving/question_catalog.md`
  (guardrail precedent this module carries forward), `CLAUDE.md` (the
  operational MCP-gate summary and the standing guardrail copy),
  `src/dbt/models/intermediate/int_support_tickets.sql` +
  `src/dbt/models/gold/fct_reviews.sql` (the RAG-corpus gap)
- Databricks docs / skills used: `databricks-vector-search`,
  `databricks-agent-bricks`, `databricks-mlflow-evaluation`,
  `databricks-bundles` (for the DAB-resource-type check named in §6.3)
- External: ___

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-24 | Module scaffolded during `v0.6` scoping. RAG-before-text-to-SQL sequencing and the RAG-corpus/PII gaps named explicitly (§5); step-groups A/B laid out in §6. Build not started — this is the scoping-only artifact per `docs/adr/0009-*.md`. | Chirag + Claude |
