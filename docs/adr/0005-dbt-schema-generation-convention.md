# ADR-0005: Override `generate_schema_name` so dbt schemas map 1:1 to Unity Catalog

**Status:** Accepted
**Date:** 2026-07-16
**Related:** [ADR-0002](0002-use-dbt-for-silver-gold.md)

## Context

dbt's default `generate_schema_name` macro concatenates the profile's target
schema with a model's `+schema` config (`<target_schema>_<custom_schema>`) — e.g.
target `silver` + `+schema: gold` would produce a table in `silver_gold`, not
`gold`. This repo's naming convention (`docs/00-setup.md` §5) is
`novalake.<layer>.<object>` — `bronze`, `silver`, `gold`, `serving` as exact
schema names. Left at its default, dbt's first model would already violate that
convention, and the mismatch would compound as more `+schema` overrides are added
across Silver and Gold.

This is a one-time convention decision that affects every future model in the
project, not a one-off fix — worth its own ADR rather than a buried comment, so a
future contributor (or future me) doesn't wonder why a `models/staging/` folder is
landing in schema `silver` with no `staging` schema anywhere in Unity Catalog.

## Decision

Override `generate_schema_name` in `src/dbt/macros/generate_schema_name.sql` to
return the `+schema` value directly when set (falling back to the profile's
target schema otherwise), so `+schema: silver` / `+schema: gold` resolve to
exactly `novalake.silver` / `novalake.gold` — no concatenation. Also documented in
`dbt_project.yml`: `stg_raw_events` living in schema `silver` is deliberate — dbt's
"staging" naming convention and this project's "Silver" medallion layer are being
treated as the same thing on purpose, not a naming oversight.

## Consequences

- Every dbt model's actual Unity Catalog location is exactly what its `+schema`
  config says, matching `docs/00-setup.md`'s naming convention with no mental
  translation required.
- Losing dbt's default per-target schema isolation (e.g. a `dbt_<user>` dev
  sandbox schema) is an accepted tradeoff for now — see
  [ADR-0004](0004-local-dbt-development-workflow.md)'s note that local dev and the
  job currently share the same schemas.
- Any new model needs an explicit `+schema` (inherited from `dbt_project.yml`'s
  folder-level config, or set per-model) — there's no more "custom schema is
  optional, it'll just get appended" default to fall back on.

## Alternatives considered

- **Leave the default macro in place, rename schemas to match dbt's
  concatenation.** Rejected — would mean bending Unity Catalog's schema names to
  fit dbt's convention instead of the other way around, breaking the project's
  own pre-existing naming convention for every non-dbt tool that also touches
  these schemas.
