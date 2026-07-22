# ADR-0008: NovaLake terminus at v0.9; production semantics and Terraform IaC succeed to Cerberus

**Status:** Accepted
**Date:** 2026-07-22
**Related:** [ADR-0007](0007-defer-prod-no-same-workspace-production-semantics.md)

## Context

ADR-0007 established that real production semantics — a genuinely
separate environment, actual promotion, and infrastructure reproducible
from scratch — cannot exist inside NovaLake's single Free Edition
workspace, and left open where they should live. An earlier draft
answered "a second Databricks workspace, reproduced via IaC (Terraform
the leading candidate)." Examining that option alongside NovaLake's
remaining learning value surfaced a better shape for the whole portfolio.

Two findings drove this:

1. **A second Free Edition/serverless Databricks workspace teaches almost
   nothing new.** It reproduces the same serverless abstraction: the same
   locked Spark configs, managed compute, absent knobs. A second Free
   Edition account also strains the intent of the fair-use policy. (A
   *paid* Databricks workspace on classic, non-serverless compute would
   genuinely expose the missing knobs — see Alternatives — but that's a
   different option than "a second Free Edition workspace," and isn't
   what the earlier draft actually proposed.)
2. **Serverless structurally caps NovaLake's optimization ceiling.**
   Serverless compute exposes no Spark UI and no cluster-sizing knobs,
   and most `spark.conf` settings are locked. Query profile and
   `EXPLAIN` plans *are* available on serverless — the query/data-layout
   half of Spark optimization is fully in reach there. What's out of
   reach is the infrastructure-tuning half (executor/shuffle tuning,
   cluster sizing, disk-cache control) — RDD-level caching APIs are
   unsupported and DataFrame `.cache()`/`.persist()` aren't meaningfully
   tunable on serverless, so that half is capped by the platform, not by
   effort.

## Decision

**NovaLake gets a defined terminus. Its deferred ambitions succeed to a
new project, Cerberus, on AWS.**

### NovaLake terminus

- **`v0.9` is the final numbered phase**: Spark optimization *within
  serverless constraints*, capped deliberately at the query/data-layout
  layer — query profiles, `EXPLAIN` plans, liquid clustering,
  `OPTIMIZE`/file compaction, join strategy, skew handling, UDF
  elimination.
- **`v0.8` is reserved, not yet scoped.** Left as an explicit gap rather
  than silently skipped — this ADR doesn't invent content for it. If a
  concrete need surfaces before `v0.9` starts (e.g. promoting the existing
  cross-cutting governance/observability row to a numbered phase), it
  fills the slot; otherwise the roadmap collapses `v0.7` → `v0.9` directly
  and this note is updated to say so.
- **Prerequisite for v0.9**: regenerate synthetic payments data at GB
  scale (tens of millions of events). Optimization findings on the
  current 5–13 MB datasets would be noise, not engineering.
- NovaLake completes as: ingestion → Silver → Gold → serving (dashboard
  + agent), CI/CD, optimization-within-constraints. Tagged, documented,
  feature-frozen except maintenance.

### Cerberus succession

- **Cerberus** is a new data platform on AWS, built
  infrastructure-first with **Terraform** as the IaC spine, in parallel
  with cloud engineering coursework. Genuinely separate dev/prod
  environments, real promotion, and reproduce-from-nothing IaC are
  first-class concerns there — because AWS actually exposes them.
- **NovaPay** (the existing Go payments application) becomes Cerberus's
  upstream data producer, closing the loop: application (Go/NovaPay) →
  platform (Cerberus) → infrastructure (Terraform), all owned
  end-to-end. NovaLake's synthetic generators are retired in Cerberus;
  application-emitted events replace them.
- **Spark mastery splits deliberately across the two platforms**:
  NovaLake covers the half serverless exposes (query/layout
  optimization); Cerberus, on classic/self-managed compute (EMR the
  leading candidate), covers the half serverless hides (cluster sizing,
  Spark UI, executor/shuffle tuning, caching strategy). Neither platform
  pretends to teach what its compute model forbids.

## Consequences

- `README.md`'s roadmap gains `v0.8` (reserved) and `v0.9` rows, and
  becomes closed-ended: terminus stated explicitly, Cerberus named as
  successor, the open-ended "future IaC reproduction / second workspace"
  idea removed.
- The Terraform question is resolved by dissolving it: Terraform is
  Cerberus's IaC tool for AWS infrastructure; DAB remains NovaLake's
  deployment tool for Databricks resources. Different tools, different
  layers, no conflict — "Terraform vs. DAB" was an artifact of the
  now-rejected second-workspace framing.
- `docs/checkpoint.md` gains a pinned entry for the `v0.9` prerequisite
  (GB-scale data regeneration) so optimization work doesn't start on
  toy-sized data.
- Cerberus scoping (EMR vs. alternatives, AWS account structure, whether
  NovaPay needs event-emission work first) is out of scope here and
  belongs to Cerberus's own ADR-0001.

## Alternatives considered

- **Second Databricks workspace reproduced via IaC (the earlier draft's
  plan), Free Edition/serverless.** Rejected — same abstraction, no new
  knobs, fair-use strain for low marginal learning.
- **Paid Databricks workspace on classic (non-serverless) compute.**
  This genuinely would expose the missing knobs (Spark UI, cluster
  sizing, executor/shuffle tuning) while staying on Databricks/DAB — it
  is not technically ruled out the way a second serverless workspace is.
  Rejected on portfolio grounds instead: the goal is deliberate breadth
  (AWS, Terraform, and closing the loop with NovaPay as an upstream
  producer, alongside cloud-engineering coursework already in progress),
  not the cheapest path to the same Spark-tuning knowledge. Recorded
  honestly as a real, viable alternative that was passed over by choice,
  not because Databricks is structurally incapable of it.
- **Fold Spark infra-tuning into NovaLake v0.9 anyway.** Rejected —
  writing about executor memory and shuffle partitions in an environment
  that structurally forbids setting them would be unverifiable content,
  violating the project's empirical-discovery principle. Infra-tuning
  belongs where the knobs exist: Cerberus (or a classic-compute
  Databricks workspace, per the alternative above — Cerberus was chosen
  for the portfolio reasons stated, not because this specific gap
  required leaving Databricks).
- **Keep NovaLake open-ended with no terminus.** Rejected — an
  open-ended project accumulates "someday" items instead of finishing.
  A defined terminus makes NovaLake a complete, tellable story and gives
  Cerberus a clean starting thesis rather than being NovaLake-on-AWS.
