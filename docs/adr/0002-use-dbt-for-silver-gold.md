# ADR-0002: Use dbt for Silver→Gold, defer Declarative Pipelines to `v0.7`

**Status:** Accepted
**Date:** 2026-07-16
**Related:** [ADR-0001](0001-adopt-dab-from-v0.1.md)

## Context

The original roadmap planned Lakeflow Declarative Pipelines (DLT) as the Silver→
Gold transform layer, introduced at `v0.6` after a hand-written-Jobs phase at
`v0.5`. The project owner's new workflow instead specifies dbt for this layer —
SQL models with tests, the project's stated "SDLC layer": version-controlled,
tested, environment-aware.

This is a genuinely different choice from Declarative Pipelines, not a renaming
of the same thing — dbt is SQL-model-and-test-centric with its own CLI/dev loop;
Declarative Pipelines is a Spark-native declarative ETL framework with built-in
expectations and streaming-table semantics. Silently dropping Declarative
Pipelines from the roadmap to make room for dbt would remove a stated learning
goal ("Declarative ETL, DQ-as-code") without a recorded reason — worth its own
decision rather than an implicit side effect of the tooling swap.

## Decision

dbt becomes the primary Silver→Gold path starting at `v0.2`. Lakeflow Declarative
Pipelines is **not dropped** from the project's scope — it moves to a new `v0.7`
phase: re-implement part of Gold with Declarative Pipelines once the dbt approach
is understood, and compare the two directly. This keeps the project's own stated
pattern (understand one abstraction before adopting the next) intact, just applied
to comparing two Silver/Gold tools instead of sequencing DAB.

## Consequences

- `src/dbt/` becomes the home for all Silver/Gold modeling logic and tests,
  starting with `models/staging/stg_raw_events.sql` as a proof-of-wiring slice
  (see [ADR-0004](0004-local-dbt-development-workflow.md) for how it's developed).
- The 5-problem Silver scope identified in `docs/01-bronze.md` §8 (struct
  collapse, type-equivalent collapse, key renaming, structural reshaping, value
  dirtiness) gets solved in dbt models, not Declarative Pipeline expectations.
- The "Declarative ETL, DQ-as-code" learning goal is preserved, just resequenced
  to `v0.7`, after dbt — not lost.
- Two Silver/Gold implementations of the same layer will eventually exist in the
  repo (dbt now, DLT later, for comparison) — expected and intentional, not
  duplication to clean up.

## Alternatives considered

- **Keep Declarative Pipelines as the only Silver/Gold path, drop dbt.** Rejected
  — doesn't match the workflow the project owner explicitly asked for, and loses
  the "SQL models + tests as the SDLC layer" framing that motivated the pivot.
- **Drop Declarative Pipelines from the roadmap entirely.** Considered and
  explicitly rejected by the project owner when asked directly — the comparative
  learning value of implementing the same layer two ways was worth keeping.
