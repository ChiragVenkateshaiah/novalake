# ADR-0007: Defer `prod` — no same-workspace production semantics

**Status:** Accepted
**Date:** 2026-07-22
**Supersedes:** the `prod`-at-`v0.5` timing in [ADR-0003](0003-dev-only-bundle-target.md) (ADR-0003 itself remains Accepted for its other content — see its own Status note)
**Related:** [ADR-0006](0006-secret-based-service-principal-auth-for-cicd.md), [ADR-0008](0008-novalake-terminus-and-cerberus-succession.md)

## Context

[ADR-0003](0003-dev-only-bundle-target.md) deferred scaffolding a `prod`
target until `v0.5`, reasoning that a `prod` identical to `dev` in every
practical way (same single Free Edition workspace, no service principal, no
CI trigger) would be unused scaffolding. `v0.5` is that point.

A first pass at this module did add a `prod` target: same workspace, same
`novalake` catalog, distinguished only by deploying identity
(`novalake-cicd` service principal vs. Chirag's personal profile),
`mode: production`, and a separate `root_path`/resource identity to avoid
colliding with `dev`'s already-deployed job and dashboard. Reviewing that
design surfaced the actual problem: it's a semantic overlay, not real
environment isolation. The data is identical either way, deployed to the
same catalog; "promoting to prod" would mean nothing more than "the robot
deployed it instead of the human." Free Edition has exactly one workspace,
and no scaffolding within `databricks.yml` changes that fact.

## Decision

No `prod` target for NovaLake. `v0.5`'s CI/CD (`bundle-validate.yml`,
`bundle-deploy.yml`) targets `dev` — the same job and dashboard Chirag has
been deploying by hand — using the `novalake-cicd` service principal
instead of a personal profile.

Real production semantics (a genuinely separate environment, actual
promotion between environments, and infrastructure proven reproducible
from scratch rather than re-deployed in place) are **not** achievable
within this workspace and are not simulated here. Where they live instead
is a portfolio-level decision recorded separately in
[ADR-0008](0008-novalake-terminus-and-cerberus-succession.md).

## Consequences

- `v0.5`'s CI/CD is real (a working GitHub Actions gate + deploy against
  live resources), just narrower in scope than "prod" implies — it
  automates `dev`, it doesn't introduce a second environment.
- `novalake-cicd` needed explicit, scoped grants to manage `dev`'s
  existing job/dashboard/bundle-folder (it isn't the identity that
  originally created them) — done as part of this same `v0.5` work, and a
  deliberately narrower grant than the workspace-admin access it got by
  default when created (see `docs/checkpoint.md`, 2026-07-22).
- The question "where do real production semantics eventually live" is
  deliberately left open by this ADR and answered by ADR-0008.
- `README.md` still had three stale references to a `prod` target from
  the first-pass design (roadmap's `v0.5` row, the repo-structure comment
  on `databricks.yml`, and the Status section) — all three needed
  correcting to reflect "automates `dev` deploy via service principal,"
  not a `prod` target that no longer exists.

## Alternatives considered

- **Same-workspace `prod` target (the first pass at this ADR).**
  Rejected — doesn't test reproducibility, only relabels who deploys to
  the one environment that exists. Would have added real complexity
  (target-conditional resource identity to avoid dashboard recreates,
  a second root_path, its own grants) for a distinction without a
  difference.
- **Skip CI/CD entirely until a second environment exists.** Rejected —
  the PR-validation gate and taking over `dev`'s deploy from a personal
  profile to a scoped service principal are real, valuable improvements
  on their own, and don't need to wait on a decision about future
  environments.
