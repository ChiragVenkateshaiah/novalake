# Checkpoint — Agentic Integration (Claude Code + Databricks MCP)

**Status:** 🟢 Revised 2026-07-16 — see "Revised decision" below. The original
"DAB later" timing was reversed; the underlying agentic-integration principle
(no agent-authored IaC until its author has written the equivalent by hand) is
unchanged and still governs everything below.
**Opened:** Project kickoff (v0.0)
**Re-open at:** start of `v0.5` (CI/CD) — decide go/no-go for agent-authored CI
config for real. (Original text referenced `v0.5` Lakeflow Jobs / `v0.6`
Declarative Pipelines; those phases were renumbered/replaced by the roadmap pivot
below — see "Revised decision.")

> This file exists so the decision below doesn't get re-litigated or forgotten three
> phases from now. It's the one thing in this repo that documents a *process* choice
> rather than a *data* one — closer to a software engineering ADR than a data-eng doc.

---

## The question

Should Claude (via Claude Code CLI) be wired into this project's Databricks Asset
Bundle / MCP servers from the start, so it can author and deploy infrastructure
directly?

## The decision

> **2026-07-16:** the *timing* below was revised — see "Revised decision" further
> down this file. The principle stated here (no agent-authored IaC until its
> author has written the equivalent by hand) still governs; only when DAB
> itself was introduced changed. Read this section as history, not current
> status.

**Not yet.** Agent involvement in the orchestration/IaC layer is deferred until:

1. `v0.5` is done by hand — a real `databricks.yml` and job resources, hand-written,
   manually deployed with `databricks bundle deploy`. No agent touches this file
   until its author has written one from scratch and knows what correct output
   looks like.
2. `v0.6` is underway — at this point we design the actual agentic-integration
   architecture (Claude Code CLI + Databricks MCP servers) and start using it for
   real, with a human-review gate on every diff before deploy.

Everything before that (Bronze through Serving, v0.0–v0.4) stays hands-on: notebooks
and SQL written manually, Claude acting as architect/reviewer in chat — not as an
agent with repo or workspace write access.

## Why

- **Sequencing mirrors the rest of this project.** We deliberately do Jobs by hand
  before Declarative Pipelines, so the abstraction is understood before it's adopted.
  The same logic applies one layer up: understand DAB by hand before an agent writes
  it for you.
- **Foundation before automation.** The most common reason agentic data projects
  stall isn't the agent — it's a shaky foundation underneath it (unclear schemas,
  no lineage, inconsistent definitions). Phases v0.0–v0.4 *are* that foundation
  work. Building it manually is also what makes the eventual reviewer (you)
  qualified to review what an agent produces on top of it.
- **This matches how the industry is actually doing it, not skipping it.**
  The pattern that's converged across both general agentic-coding practice and
  Databricks' own Genie Code is "agent proposes, human reviews the plan/diff,
  CI validates, then deploy" — not full autonomy. Connecting Claude to DAB later
  is adopting that pattern properly, not lagging behind it.

## What to design when we get here (not now — just the shape)

- **Integration surface:** Databricks-managed MCP servers (Unity Catalog functions,
  AI Search indexes, Genie spaces) as the connective tissue, rather than anything
  bespoke — this is the standard way agents reach Databricks tools as of 2026.
  Reference: `docs.databricks.com` → *Use Databricks managed MCP servers*.
  Compare against the Databricks AI Dev Kit's Genie Code skills for Asset Bundles
  as a pattern reference (`github.com/databricks-solutions/ai-dev-kit`).
- **Local pattern to reuse:** the same `CLAUDE.md`-driven, repo-aware Claude Code
  CLI setup already running on NovaPay — same discipline, new repo.
- **Review gate:** every Claude Code diff against `databricks.yml` / `resources/*`
  reviewed before `databricks bundle deploy`, the same way a human PR would be.
- **CI gate:** `databricks bundle validate` in GitHub Actions on every PR, before
  merge — gives the agent a checked boundary, not a blank check.
- **Scope at first:** start narrow — let the agent draft *one* job/pipeline resource
  and review it line by line, before trusting it with the full bundle.

## Revised decision (2026-07-16)

The sections above are left as-written — this is a deliberate reversal, recorded
as one, not a silent overwrite of the original reasoning.

Two things changed, both decided directly with the project owner, not assumed:

1. **DAB adopted from `v0.1` onward, not deferred to the old `v0.5`.** The
   workflow now under construction — PySpark (Bronze) / dbt (Silver→Gold) / Genie
   (Serving) / DAB (deploy wrapper) — treats the bundle as part of the
   architecture from day one, not an add-on bolted on after four phases of
   notebooks. This does **not** violate the original "understand it by hand
   before automating" principle above: `databricks.yml` and
   `resources/dbt_job.yml` are still hand-authored, reviewed line by line, with
   no agent given repo or workspace write access to author or deploy them. Only
   the *timing* of DAB's introduction changed — the human-before-agent sequencing
   this checkpoint exists to protect did not.
2. **dbt adopted as the primary Silver→Gold path, replacing Lakeflow Declarative
   Pipelines in that role.** SQL models + tests fit the "SDLC layer" goal
   (version-controlled, tested, environment-aware) better than a pipeline-only
   approach for this phase. Declarative Pipelines is **not dropped from the
   project's scope** — it's deferred to a later comparative-learning phase
   (`v0.7`): re-implement part of Gold with DLT once the dbt approach is
   understood, and compare the two, consistent with this repo's own pattern of
   understanding one abstraction before adopting the next.

Net effect on the roadmap: old `v0.5` (Lakeflow Jobs) and `v0.6` (Declarative
Pipelines) are retired as separate phases; DAB is folded into `v0.1` onward, dbt
becomes `v0.2`/`v0.3`, and a new `v0.5` (CI/CD) and `v0.7` (Declarative Pipelines,
comparative) take their place. See `README.md` roadmap table for the current
numbering.

Formal decision records: [`docs/adr/0001`](adr/0001-adopt-dab-from-v0.1.md) (DAB
timing) and [`docs/adr/0002`](adr/0002-use-dbt-for-silver-gold.md) (dbt vs.
Declarative Pipelines) — this section is the narrative; those are the one-
decision-per-file record. See [`docs/adr/`](adr/) for the rest (dev-only bundle
target, local dbt workflow, dbt schema convention) — smaller decisions this
reversal produced that don't belong in this single-topic checkpoint file.

## Revisit log

| Date | Note |
|------|------|
| v0.0 | Checkpoint opened. Plan above agreed. |
| 2026-07-16 | DAB-timing and Silver/Gold-tooling decisions reversed (DAB from `v0.1`, dbt replaces Declarative Pipelines as primary Silver/Gold path; DP deferred to `v0.7` as a comparative exercise). See "Revised decision" above. Original reasoning left intact. |
