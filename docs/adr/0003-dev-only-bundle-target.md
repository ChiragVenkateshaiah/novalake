# ADR-0003: Keep `databricks.yml` dev-only until `v0.5` (CI/CD)

**Status:** Accepted
**Date:** 2026-07-16
**Related:** [ADR-0001](0001-adopt-dab-from-v0.1.md)

## Context

Standard DAB examples default to scaffolding both `dev` and `prod` targets from
the start (see the `databricks-bundles` skill reference pattern). This repo has
its own stated principle, though — from `README.md` and `docs/checkpoint.md` — of
not pre-scaffolding folders or resources ahead of the phase that actually needs
them (`pipelines/`, `resources/`, `databricks.yml` were all "created when their
phase starts, not pre-scaffolded" under the original plan).

A `prod` target today would be identical to `dev` in every practical way: same
single Databricks Free Edition workspace, no service principal, no CI trigger,
`mode: production`'s validation semantics (run-as identity, root path
restrictions) buying nothing with one PAT-authenticated user. It would exist only
as unused scaffolding.

## Decision

`databricks.yml` defines a `dev` target only. `prod` is added at `v0.5` (CI/CD),
at the same time as the service-principal deploy and GitHub Actions workflow that
actually give a `prod` target meaning.

## Consequences

- `databricks bundle deploy` (no `-t` flag) always targets `dev` by default —
  no risk of accidentally deploying to an undifferentiated "prod" that isn't
  really production-hardened yet.
- When `v0.5` adds `prod`, it arrives together with the service principal and CI
  gate that make the distinction real, rather than as a placeholder that sat
  unused for four phases.

## Alternatives considered

- **Scaffold `dev`/`prod` now for a "complete-looking" bundle.** Rejected —
  directly contradicts this repo's own stated anti-pre-scaffolding principle, and
  the `prod` target would have no real content until `v0.5` anyway.
