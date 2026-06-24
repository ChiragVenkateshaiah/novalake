# Checkpoint — Agentic Integration (Claude Code + Databricks MCP)

**Status:** 🟡 Pinned — not yet started
**Opened:** Project kickoff (v0.0)
**Re-open at:** start of `v0.5` (Lakeflow Jobs), decide go/no-go for real at `v0.6` (Declarative Pipelines)

> This file exists so the decision below doesn't get re-litigated or forgotten three
> phases from now. It's the one thing in this repo that documents a *process* choice
> rather than a *data* one — closer to a software engineering ADR than a data-eng doc.

---

## The question

Should Claude (via Claude Code CLI) be wired into this project's Databricks Asset
Bundle / MCP servers from the start, so it can author and deploy infrastructure
directly?

## The decision

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

## Revisit log

| Date | Note |
|------|------|
| v0.0 | Checkpoint opened. Plan above agreed. |
