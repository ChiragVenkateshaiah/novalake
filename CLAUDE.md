# NovaLake — CLAUDE.md

**Open item:** `docs/checkpoint.md` names "the same `CLAUDE.md`-driven,
repo-aware Claude Code CLI setup already running on NovaPay" as the pattern
to reuse for this file. Checked directly: `~/novapay-app` (the actual
payments-platform project this README describes) has no `CLAUDE.md`. A
different, related repo (`~/novapay-sre`) has one, but that isn't what
checkpoint.md meant, so this file is derived from NovaLake's own docs
instead rather than borrowing another project's content. If Chirag later
finds or writes NovaPay's own `CLAUDE.md`, diff it against this one for
anything genuinely worth reusing.

## What this project is

A hands-on Databricks lakehouse build, end to end: raw event data → Bronze
(PySpark) → Silver → Gold (dbt) → Serving (Genie + dashboard) → a GenAI
layer on top of the same curated data — orchestrated by a Databricks Asset
Bundle (DAB) from the first phase onward. Built on Databricks Free Edition,
documented as it's built, every transformation and decision versioned in
this repo. This is a learning project run with real engineering hygiene —
partly because the discipline is the point, partly because it's also a
portfolio artifact. Full architecture diagram and roadmap: `README.md`.

NovaLake is the analytical/AI counterpart to **NovaPay** (a separate
payments-platform project) — NovaPay generates the operational event stream;
NovaLake is the lakehouse that turns it into business metrics, served
dashboards, and a support-assist AI agent.

## Current phase

Don't duplicate phase status here — it goes stale fastest. Check
`README.md`'s **Status** section for what's shipped vs. in progress, and the
**Roadmap** table for what's next.

## Repo structure

Don't duplicate the tree here — same staleness risk as phase status, and it
already drifted once. **`README.md`'s "Repo structure" section is the source
of truth**, kept current as each phase adds files.

One standing principle worth restating because it governs what *not* to
create: `pipelines/` and any `v0.6` GenAI source directory (e.g.
`src/genai/`, `resources/vector_search.yml`) are **not pre-scaffolded** —
this project doesn't create a phase's structure ahead of the phase that
needs it (see `docs/checkpoint.md`). Don't create them speculatively.

## Branch / commit / tag conventions

From `CONTRIBUTING.md`, verbatim:
- `main` is always the last known-good state. One branch per module
  (`feat/v0.1-bronze`, `feat/v0.2-silver`, ...). Merge to `main` only when
  that module's Definition of Done (below) is met.
- Commits: [Conventional Commits](https://www.conventionalcommits.org/) —
  `feat(silver): explode line_items and flatten payment_method struct`,
  `fix(bronze): correct rescued-data column name`, `docs(v0.2): fill
  validation + knowledge check sections`.
- Tag `main` at the end of each module: `v0.0`, `v0.1`, `v0.2`, ... Tag
  message = one-line summary of what now works.

## Definition of Done (per module)

From `CONTRIBUTING.md`, verbatim:
- [ ] Table(s)/asset(s) created and queryable
- [ ] Logic committed under the layer's actual home: `src/ingest.py`
      (Bronze), `src/dbt/models/<layer>/` (Silver/Gold, dbt tests passing),
      `resources/` (DAB job/task definitions), or `notebooks/<phase>/` for
      historical/exploratory work not promoted to a script
- [ ] `docs/<NN>-<phase>.md` filled in — sections 1–9 at minimum, not just
      headers
- [ ] Validation checklist in that doc is green
- [ ] Tagged release pushed

## Doc convention

Every phase gets a `docs/NN-phase.md` following `docs/_skeleton.md`'s fixed
12-section template + Changelog (Learning Objectives, Prerequisites, Where
This Fits, Concepts & Background, Data Contract, Step-by-Step
Implementation, Operational Considerations, Data Quality & Governance,
Validation & Acceptance Criteria, Key Takeaways, Knowledge Check,
References). Don't invent a different structure for a new phase doc — copy
the skeleton.

## ADR convention

Architecture/process decisions that would otherwise get re-litigated get an
immutable, Nygard-style ADR under `docs/adr/000N-*.md` (Context / Decision /
Consequences / Alternatives considered) — one decision per file, `Status`
changes only via a note like "Superseded by ADR-000X," never a silent edit.
Significant ADRs go through a second-model-pass (Opus) review before
acceptance — see `docs/adr/README.md` for the index and the review
precedent (ADRs 0001–0005, 0007–0009 all went through this).

## `docs/checkpoint.md` — the one file with a different shape

`checkpoint.md` tracks exactly one running question — when/how Claude gets
agentic/workspace-write access — as a single-topic, dated revisit log, not a
collection of one-decision-per-file ADRs. Don't "ADR-ify" it: new
developments on that question get appended as a dated row to its existing
revisit-log table, not split into a new file, and its narrative sections
(the original decision, the 2026-07-16 and later revisions) stay in place as
history even after being superseded — matching the same
narrate-the-reversal-don't-silently-edit discipline the ADRs use. Read this
file at the start of any session touching Claude's access to the workspace.

## Agentic access: MCP-gated review-then-act (from v0.6 onward)

Formal record: [`docs/adr/0009-agentic-integration-mcp-gated-review-then-act.md`](docs/adr/0009-agentic-integration-mcp-gated-review-then-act.md).
Operational summary — this is what actually governs behavior day to day:

- **Before any Databricks MCP action with side effects** (create/modify a
  Vector Search endpoint/index, an Agent Bricks resource, a UC object,
  etc.), state the **exact tool call and its full parameter set** — not a
  prose summary — and wait for Chirag's explicit go-ahead. Match the
  specificity of an ADR (exact IDs, exact parameters), not a paraphrase.
- **Read-only, ungated:** `list`/`get` calls, `query_vs_index`,
  `execute_sql`/`execute_sql_multi` when the statement is
  `SELECT`/`SHOW`/`DESCRIBE`/`EXPLAIN` only.
- **Gated, named explicitly (don't assume anything not listed here is
  safe):** `execute_code`; any non-`SELECT` `execute_sql`; `manage_vs_endpoint`,
  `manage_vs_index`, `manage_vs_data` (an index *upsert* is a write, not
  "just search"); `manage_genie`/`manage_ka`/`manage_mas` create/update/
  delete; `manage_uc_objects`, `manage_uc_grants`/`manage_uc_security_policies`,
  `manage_workspace`/`manage_workspace_files` writes.
- **Every executed gated action gets logged to `docs/checkpoint.md`'s
  revisit-log** — dated, naming the tool call, parameters, and outcome. File
  changes are already visible in git history; live MCP actions are not.
- **Deleting a wrongly-created live resource is itself a gated action** —
  not something to clean up unilaterally.
- Identity-sensitive actions (new service principals/secrets) stay hands-on
  regardless — Chirag creates these himself.
- `bundle validate` remains the CI gate for anything also expressed as
  bundle IaC — this doesn't replace the file-diff+PR path where DAB already
  supports a resource type, it covers the genuine gap.
- Before `v0.6`, this project ran a stricter pattern per phase (hands-off
  entirely through `v0.4`, "Claude drafts files, Chirag runs everything" at
  `v0.5`) — see `docs/checkpoint.md`'s revisit log for the full history if
  precedent for a specific situation is useful.

## Known data guardrails

These exist because a capable text-to-SQL or RAG-answering model can find
and misuse a technically-valid-looking join or blend that a human wouldn't —
the same reasoning `docs/serving/genie_space.md` documents for why some of
these are enforced by *excluding* a column, not just instructing against it.
Treat these as binding for any query, dashboard tile, Genie answer, or
GenAI-agent response, not just the existing serving layer:

1. Never combine fx-normalized USD totals (only exist for `multiline`) with
   native-currency totals from `ndjson` into one figure. Label any USD total
   as multiline-only.
2. Never blend support-ticket performance across sources. `resolution_minutes`
   (real elapsed time) exists only for `ndjson`; `sla_breached`/
   `sla_target_minutes` (target/breach flag) exist only for `multiline`.
   Report these as two separate answers, never one blended number.
3. Never join `fct_refunds` or `fct_support_tickets` to `fct_transactions` on
   `original_transaction_id` or `related_transaction_id` — both are
   independently random UUIDs in both source generators, not real foreign
   keys, and were deliberately excluded from the Genie space's column
   visibility for exactly this reason. Use aggregate ratios grouped by
   `(event_date, source)` instead.
4. Every `metric_*` table's rate column (`approval_rate`, `decline_rate`,
   `refund_rate`, `sla_breach_rate`, `verified_purchase_rate`) is
   pre-computed at a specific grain. Any question spanning a coarser grain
   must recompute the rate from the underlying counts each metric table also
   exposes — never average the rate column itself (Simpson's-paradox trap).

Full instruction set (including expected-data-quirk notes, not just these
adversarial-misuse guardrails) and the certified question→SQL pairs that pin
trusted answers for the highest-risk questions: `docs/serving/genie_space.md`,
`docs/serving/question_catalog.md`.

## Raw data / free-text policy

Raw JSON payloads are **not** committed to Git — they live in
`novalake.bronze.landing` (a Unity Catalog Volume). Only generator scripts
(`data/generators/`) and data dictionaries (`data/dictionaries/`) are
version controlled. As of `v0.5`, free-text fields relevant to a future
GenAI/RAG layer are **not fully promoted to Gold yet**: `fct_support_tickets`
carries `subject` but not `description`/`messages[]` (Silver-only, per a
standing comment in `int_support_tickets.sql`); `fct_reviews` excludes
`title`/`body` entirely (same GenAI-deferral precedent). Don't assume these
fields are queryable from Gold without checking current state first.
