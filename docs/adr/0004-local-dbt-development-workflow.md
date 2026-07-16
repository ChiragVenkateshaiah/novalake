# ADR-0004: Develop dbt locally; reserve the DAB `dbt_task` for orchestrated runs

**Status:** Accepted
**Date:** 2026-07-16
**Related:** [ADR-0002](0002-use-dbt-for-silver-gold.md)

## Context

Once dbt was chosen for Silver→Gold ([ADR-0002](0002-use-dbt-for-silver-gold.md)),
a real question followed: where does dbt actually run day to day — locally, or
only through the DAB `dbt_task` in `resources/dbt_job.yml`?

Running dbt only through the job means every model change requires
`databricks bundle deploy` + `databricks bundle run`, waiting for a cloud job to
start and execute, then reading logs to see if a single SQL edit worked. dbt's
entire value proposition is a fast local edit → `dbt run` → `dbt test` loop
against a real warehouse; routing that loop through a full job deploy on every
change defeats the tool's own design.

## Decision

Install dbt locally (`requirements-dbt.txt`, `dbt-databricks`) and develop against
it directly via `dbt_profiles/profiles.yml` (`host`/`http_path` from
`DATABRICKS_HOST`/`DATABRICKS_HTTP_PATH` env vars), targeting the same
`novalake.silver`/`novalake.gold` schemas the job writes to. The DAB `dbt_task` is
for orchestrated and eventually scheduled/CI-triggered runs — not the primary
development loop.

Auth uses `auth_type: oauth` rather than a static token — `databricks auth
describe -p DEFAULT` confirmed the CLI's own profile is already OAuth
(`databricks-cli` auth type). dbt-databricks doesn't accept that literal value
(found via `dbt debug` failing with "auth_type: oauth is required"), but `oauth`
shares the same token cache (`~/.databricks/token-cache.json`) and reused the
existing session with no new browser flow. No PAT to generate, store, or rotate.

## Consequences

- Local dbt needs two env vars set (`DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`)
  pointed at the same SQL warehouse the bundle uses (`8fd481cbf45ac93e`,
  "Serverless Starter Warehouse") — one-time setup per machine. No token env var,
  no secret in `dbt_profiles/profiles.yml` at all; auth flows through the
  `databricks` CLI's own credential cache.
- Local dev and the job both write to the same `novalake.silver`/`novalake.gold`
  schemas — no separate "local sandbox" schema exists yet. Acceptable for a
  solo project at this phase; worth revisiting if this becomes a concern later
  (e.g. a per-developer schema suffix).
- The job's `dbt_task` omits `profiles_directory`, on the assumption that a
  job-managed dbt task auto-generates its own Databricks auth — **confirmed** by
  a real `databricks bundle run`: auth was never the problem. What the first real
  run *did* surface, which no amount of `bundle validate` would have caught:
  serverless environments don't ship `dbt` preinstalled. The `dbt_task`'s
  `environment_key` needs `dbt-databricks` declared explicitly under
  `spec.dependencies` (see `resources/dbt_job.yml`), or `dbt run` fails with
  exit 127 ("command not found"). Split into its own `dbt_env` environment,
  separate from `bronze_ingest`'s `pyspark_env`, so the PySpark task doesn't
  carry an unused dbt dependency.

## Alternatives considered

- **Run dbt only through the DAB job, no local install.** Rejected — makes
  routine model iteration (the majority of Silver/Gold work) unacceptably slow,
  and abandons the fast local dev loop dbt is designed around.
- **A dedicated local/sandbox schema per developer.** Not adopted now — this is a
  solo project with one contributor; the added complexity isn't earning its keep
  yet. Revisit if the project gains collaborators.
