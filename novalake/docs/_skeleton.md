# Project Documentation Skeleton — NovaPay Lakehouse → GenAI

> **Purpose of this file.** A reusable, Databricks-self-paced-course-style documentation
> skeleton. It defines *structure only* — section headers and one-line intent hints,
> **no written content**. You fill each module as you build it.
>
> **How to use.** Copy `## MODULE TEMPLATE` once per phase into its own file
> (`docs/phase-1-bronze.md`, etc.), rename the banner, then keep only the sections that
> apply to that phase (the per-phase index below tells you which ones matter).

---

## Conventions (fill once, reuse everywhere)

- **Naming:** `[catalog].[schema].[table]` convention → `___`
- **Layer schemas:** `bronze`, `silver`, `gold`, `serving`, `ml` (or your choice) → `___`
- **Notebook / file naming pattern:** `___`
- **Doc status tags:** `Draft` · `Reviewed` · `Validated`
- **Diagram source of truth:** `___` (e.g. one architecture diagram referenced by every module)

---

## MODULE TEMPLATE  *(the repeating skeleton — copy this block per phase)*

### `Module N · [Phase Title]`
`Status:` ___  ·  `Owner:` ___  ·  `Last updated:` ___  ·  `Est. time:` ___

#### 1. Learning Objectives
- [ ] By the end of this module you can ___
- [ ] ___
- [ ] ___

#### 2. Prerequisites
- Completed modules: ___
- Tables / assets that must already exist: ___
- Compute / cluster config: ___

#### 3. Where This Fits (Architecture Context)
- One-line: *what this layer consumes and what it produces*
- Reference diagram: `[link/anchor]`
- Inputs → this module → Outputs: ___ → ___ → ___

#### 4. Concepts & Background
- Concept 1: ___ *(short definition / why it matters here)*
- Concept 2: ___
- Common pitfalls / gotchas to watch for: ___

#### 5. Data Contract / Schema in Scope
- Source schema (expected): ___
- Target schema (produced): ___
- Schema-evolution policy: ___
- Keys / grain / uniqueness: ___

#### 6. Step-by-Step Implementation
> Repeat this sub-block per step. Keep the headers; fill the blanks.

- **Step 6.x — [step name]**
  - *Objective:* ___
  - *Concept:* ___
  - *Task:* ___
  - *Notebook / cell reference:* ___
  - *Expected output:* ___
  - *Validation check:* ___

#### 7. Operational Considerations
- Idempotency / re-run safety: ___
- Incremental vs full refresh: ___
- Performance (partitioning / clustering / file sizing): ___
- Failure & retry behaviour: ___

#### 8. Data Quality & Governance
- Expectations / rules applied: ___
- Quarantine / reject handling: ___
- Lineage & catalog tags: ___
- Ownership & access: ___

#### 9. Validation & Acceptance Criteria
- [ ] Row-count / reconciliation check: ___
- [ ] Schema assertion: ___
- [ ] Business-rule assertion: ___
- [ ] Sign-off: ___

#### 10. Key Takeaways
- ___
- ___

#### 11. Knowledge Check
- Q1: ___
- Q2: ___

#### 12. References
- Internal: ___
- Databricks docs: ___

#### Changelog
| Date | Change | Author |
|------|--------|--------|
| ___  | ___    | ___    |

---
---

## PER-PHASE MODULE INDEX  *(skeletons — headers only, no content)*

> Each phase below lists its banner and the sections from the template that matter most.
> Sections not listed can be dropped for that phase.

### `Module 0 · Project & Environment Setup`
- 1 Objectives · 2 Prerequisites · 3 Architecture Context (the whole picture) ·
  4 Concepts (lakehouse, medallion, Unity Catalog basics) · 12 References
- Phase-specific blanks:
  - Workspace / Free Edition setup notes: ___
  - Catalog & schema creation: ___
  - Volume / upload location for the raw file: ___
  - Naming & folder conventions confirmed: ___

### `Module 1 · Bronze — Raw Ingestion`
- 1 · 2 · 3 · 4 · 5 (raw envelope schema) · 6 (ingest steps) · 7 · 8 · 9
- Phase-specific blanks:
  - Read strategy (single-line JSON vs multiline): ___
  - Raw landing table definition (append-only, as-is): ___
  - Capture of `_ingested_at`, source file, `_rescued_data`: ___
  - Decision log: what is intentionally *not* cleaned here: ___

### `Module 2 · Silver — Conform, Cleanse, Explode`
- 1 · 2 · 3 · 4 · 5 (per-event-type target schemas) · 6 (one step per transform) ·
  7 · 8 · 9
- Phase-specific blanks:
  - Polymorphic payload split strategy (one table per event type vs unified): ___
  - Schema-drift reconciliation (v1 ↔ v2 field mapping): ___
  - Type / unit normalisation (money units, currency casing, country): ___
  - Timestamp normalisation (epoch-millis vs ISO vs null): ___
  - Array flattening (`explode` vs `explode_outer`): which arrays → which tables: ___
  - Deduplication strategy (replayed `event_id`): ___
  - Malformed-record handling / quarantine: ___

### `Module 3 · Gold — Business Metrics & Aggregates`
- 1 · 2 · 3 · 5 (metric definitions) · 6 (one step per metric set) · 7 · 9
- Phase-specific blanks:
  - Metric catalogue (definition + grain + formula per metric): ___
  - Conformed dimensions (customer / merchant / date): ___
  - Example metric families: volume, approval/decline rate, refund rate, fraud
    rate, support resolution time, review sentiment rollup, payout latency: ___
  - Slowly-changing / snapshot strategy (if any): ___

### `Module 4 · Serving Layer`
- 1 · 2 · 3 · 5 · 6 · 9
- Phase-specific blanks:
  - Consumer shapes (dashboard tables vs feature tables vs API views): ___
  - AI/BI dashboard or Genie space definition: ___
  - Aggregation grain & refresh cadence per serving asset: ___

### `Module 5 · Orchestration — Lakeflow Jobs`
- 1 · 2 · 3 · 6 (one step per task) · 7 · 9
- Phase-specific blanks:
  - Task DAG (Bronze → Silver → Gold → Serving): ___
  - Triggers (schedule / file-arrival): ___
  - Parameters & job-level config: ___
  - Notifications / alerts: ___
  - Failure isolation & retry policy per task: ___

### `Module 6 · Declarative Pipeline (Lakeflow / Spark Declarative Pipelines)`
- 1 · 2 · 3 · 4 (streaming tables, materialized views, flows, expectations) ·
  6 (migration steps) · 7 · 8 (expectations) · 9
- Phase-specific blanks:
  - Migration map: which Jobs tasks → which streaming tables / materialized views: ___
  - Declarative expectations (warn / drop / fail) per table: ___
  - Full-refresh vs incremental flow choices: ___
  - What got simpler vs what you lost going declarative (reflection): ___

### `Module 7 · GenAI Serving Layer`
- 1 · 2 · 3 · 4 (RAG, embeddings, agents, evaluation) · 6 · 8 (governance of AI assets) · 9
- Phase-specific blanks:
  - Curated text corpus source (Silver/Gold: tickets, threads, reviews, notes): ___
  - Embedding + index strategy (AI Search / Vector Search): ___
  - Use case(s): support-assist RAG / customer-history summarisation /
    dispute triage / text-to-SQL over Gold via Genie: ___
  - Agent design (Agent Bricks: tools, memory, orchestration): ___
  - Evaluation approach (offline eval set, metrics, guardrails): ___
  - Serving surface (endpoint / app) & access control: ___

### `Cross-Cutting · Governance, Observability, CI/CD`  *(running appendix, not a phase)*
- Phase-specific blanks:
  - Unity Catalog: catalogs/schemas, tags, lineage, classifications: ___
  - Observability: system tables, pipeline metrics, query history: ___
  - CI/CD: Databricks Asset Bundles / repo structure / promotion flow: ___
  - Secrets & identities: ___
  - Cost notes (Free Edition quotas / serverless usage): ___
