# ADR-0001: Adopt Databricks Asset Bundles from `v0.1`, not `v0.5`

**Status:** Accepted
**Date:** 2026-07-16
**Supersedes:** the timing portion of the original decision in
[`docs/checkpoint.md`](../checkpoint.md) ("The decision" section, opened at
project kickoff), which deferred DAB to `v0.5`.

## Context

At project kickoff, `docs/checkpoint.md` deliberately deferred Databricks Asset
Bundles (DAB) to `v0.5`, on the reasoning that hand-written notebooks/SQL through
Bronze→Serving would build the foundation, and DAB would be introduced only once
that foundation — and the author's own understanding of what a hand-written bundle
looks like — was in place. That checkpoint was explicitly pinned "so it doesn't
get re-litigated or forgotten three phases from now."

It is being revisited now, deliberately, not by drift: the project owner chose to
adopt a different end-to-end workflow (PySpark for Bronze, dbt for Silver→Gold,
Genie for Serving, DAB as the deploy wrapper) where the bundle is part of the
architecture from the first phase, not an add-on introduced later.

## Decision

Adopt DAB starting at `v0.1` (Bronze). `databricks.yml` and `resources/dbt_job.yml`
are hand-authored and reviewed line by line — no agent is given repo or workspace
write access to author or deploy them. This preserves the original checkpoint's
actual protective principle (human understands and writes the bundle before an
agent ever touches it) while changing only *when* the bundle itself appears in the
project.

## Consequences

- The old `v0.5` (Lakeflow Jobs) and `v0.6` (Declarative Pipelines) roadmap phases
  are retired as separate phases; see [ADR-0002](0002-use-dbt-for-silver-gold.md)
  for where Declarative Pipelines went.
- Every phase from `v0.1` onward now has a real deploy artifact (`databricks
  bundle validate`/`deploy`) to keep correct, not just notebooks — slightly more
  surface area per phase, in exchange for not having to retrofit orchestration
  onto four phases of already-written notebooks later.
- `docs/checkpoint.md`'s agentic-integration re-open trigger moved to the new
  `v0.5` (CI/CD) phase, where the question of agent-authored CI config actually
  arises. The checkpoint's core principle (no agent-authored IaC until hand-
  authored first) is unchanged.

## Alternatives considered

- **Keep DAB deferred to `v0.5` as originally planned.** Rejected — would mean
  building `v0.1`–`v0.4` twice: once as notebooks, once retrofitted into a bundle.
  The new workflow's own logic (DAB as *the wrapper*, not a later add-on) doesn't
  fit that sequencing.
