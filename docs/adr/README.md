# Architecture Decision Records

Short, numbered records of decisions that would otherwise get re-litigated or
forgotten. Format: [Nygard-style](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
— Context, Decision, Consequences. One file per decision; immutable once
accepted except for a `Status` change (e.g. `Superseded by ADR-000X`) — corrections
get a new ADR, not a silent edit to an old one.

**Relationship to `docs/checkpoint.md`:** `checkpoint.md` is the running narrative
for the agentic-integration question specifically (single topic, revisited in
place with a dated revisit log, closer to a living design note than a decision
log). These ADRs are the formal, one-decision-per-file record for everything else.
Where the two overlap (the DAB-timing reversal touches both), `checkpoint.md`
carries the narrative and links here for the formal record.

**Source:** all five ADRs below originated from the same planning session —
[`docs/plan.md`](../plan.md), reviewed by a second model pass before execution.
See that file for the full discussion; these are the extracted, standalone
decisions.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-adopt-dab-from-v0.1.md) | Adopt Databricks Asset Bundles from `v0.1`, not `v0.5` | Accepted |
| [0002](0002-use-dbt-for-silver-gold.md) | Use dbt for Silver→Gold, defer Declarative Pipelines to `v0.7` | Accepted |
| [0003](0003-dev-only-bundle-target.md) | Keep `databricks.yml` dev-only until `v0.5` (CI/CD) | Accepted |
| [0004](0004-local-dbt-development-workflow.md) | Develop dbt locally; reserve the DAB `dbt_task` for orchestrated runs | Accepted |
| [0005](0005-dbt-schema-generation-convention.md) | Override `generate_schema_name` so dbt schemas map 1:1 to Unity Catalog | Accepted |
