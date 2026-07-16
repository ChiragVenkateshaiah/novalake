# NovaLake: pivot to PySpark(bronze) + dbt(silver/gold) + Genie(serving) + DAB(wrapper)

## Context

NovaLake's original roadmap (`README.md`, `docs/checkpoint.md`) planned hand-written
notebooks through Bronze→Serving (`v0.0`–`v0.4`), Databricks Asset Bundles (DAB)
deferred to `v0.5`, and Lakeflow Declarative Pipelines (not dbt) for the Silver/Gold
transform layer at `v0.6`. `docs/checkpoint.md` explicitly pinned the "DAB later"
decision so it wouldn't be silently re-litigated.

The user is deliberately reversing that decision: adopt DAB from now, and use dbt
for Silver→Gold — the workflow is PySpark for Bronze (genuinely messy nested JSON,
where Spark earns its place), dbt for Silver→Gold (SQL models + tests, the SDLC
layer), Genie for serving, DAB as the deploy wrapper (CLI now, CI/service-principal
later). This is a deliberate, reasoned pivot — not drift — so it gets recorded as
such in `checkpoint.md`, not silently overwritten.

Two follow-up decisions, confirmed with the user directly (not assumed):
- **Declarative Pipelines is deferred, not dropped.** dbt becomes the primary
  Silver→Gold path now, but a later phase (`v0.7`) revisits Lakeflow Declarative
  Pipelines as a second learning exercise — re-implementing part of Gold with DLT
  to compare against the dbt approach, once dbt itself is understood. The roadmap
  keeps a placeholder phase for this; it is not deleted from the project's scope.
- **`databricks.yml` stays dev-only for now.** Adding a `prod` target today would
  contradict this repo's own stated principle (`README.md`, `checkpoint.md`) of not
  pre-scaffolding ahead of the phase that needs it — `prod` arrives at `v0.5`
  (CI/CD), alongside the service-principal deploy it actually requires.

The dataset generator (`data/generators/generate_events.py`, `dataset_guide.md`,
`dataset_guide_multiline.md`) was checked and is more than sufficient: polymorphic
event types, v1/v2 schema drift, nested arrays with null/empty/missing variants,
a destructive struct-vs-string collapse (`payload.risk`), dirty categoricals,
out-of-range timestamps, replayed IDs, and (multiline variant) cross-page reference
data, dynamic-key maps, and dead-letter records. No dataset changes needed.

**Scope of this change:** repo restructuring + wiring + a first thin vertical slice
(one dbt staging model proving Bronze→dbt read access end-to-end), plus updating the
docs that describe the plan. It does **not** include designing the full Silver/Gold
model set (the 5-problem list in `docs/01-bronze.md` §8: struct collapse, type
collapse, key renaming, structural reshaping, value dirtiness) — that's real
modeling work for a follow-up session. It also does not include `.github/workflows/`
CI (explicitly "add later" per the user's own tree) or running `databricks bundle
deploy` — deploys stay manual/reviewed per `checkpoint.md`'s remaining principles.

## New repo structure

```
novalake/
├── databricks.yml              # NEW — bundle root, dev/prod targets
├── resources/
│   └── dbt_job.yml             # NEW — job: bronze ingest task -> dbt_task
├── src/
│   ├── ingest.py                # NEW — PySpark bronze ingest (ported from notebook)
│   └── dbt/                     # NEW — dbt project
│       ├── dbt_project.yml
│       ├── macros/generate_schema_name.sql
│       └── models/staging/
│           ├── _sources.yml
│           ├── _staging.yml
│           └── stg_raw_events.sql
├── dbt_profiles/
│   └── profiles.yml            # NEW — env_var()-based, for local dbt dev
├── requirements-dbt.txt        # NEW — dbt-databricks pin, for local dev
├── notebooks/01_bronze/...     # unchanged, kept as the historical v0.1 record
├── README.md                   # updated: architecture, roadmap, repo structure
├── docs/checkpoint.md          # updated: revisit log records the reversal
├── docs/01-bronze.md           # updated: pointer note to src/ingest.py, changelog
├── CONTRIBUTING.md             # updated: DoD references src/ and resources/
└── .gitignore                  # updated: dbt artifacts (target/, dbt_packages/, logs/)
```

`.github/workflows/` is not created yet — stays a documented "next" step (CI, service
principal) in the README, matching the user's own annotation.

## File-by-file plan

### `src/ingest.py` (new)
Direct port of the already-validated `notebooks/01_bronze/01_bronze_raw_event_ingestion.ipynb`
logic into a plain PySpark script suitable for a `spark_python_task`:
- `argparse` for `--catalog` (default `novalake`), so the job can pass it as a
  parameter instead of a notebook widget.
- Same behavior as today: `spark.read.json(...)` on
  `/Volumes/{catalog}/bronze/landing/payments_events.json`, add `_source_file`
  (`_metadata.file_path`) and `_ingested_at` (`current_timestamp()`), write
  `mode("overwrite")` + `overwriteSchema=true` to `{catalog}.bronze.raw_events`.
- Not redesigning to incremental/idempotent loading (Auto Loader/`COPY INTO`) in
  this pass — that's flagged as a real follow-up in the script's module docstring
  and in `docs/01-bronze.md`'s changelog, same as it was already flagged before.
- The original notebook is left in place (already tagged/validated `v0.1` work) —
  not deleted. `docs/01-bronze.md` gets a short pointer note explaining the script
  is now the forward/job-driven path.

### `src/dbt/` (new dbt project)
- `dbt_project.yml`: `profile: novalake`; `require-dbt-version: [">=1.8.0", "<2.0.0"]`
  (mirrors the `requirements-dbt.txt` pin so local and CI/job dbt versions can't
  silently drift apart); `models.novalake.staging.+schema: silver`,
  `+materialized: view` — first slice only targets Silver's schema; Gold folder
  added when Gold modeling actually starts. Note: putting `stg_raw_events` in
  schema `silver` is a deliberate choice (dbt's "staging" naming convention vs. the
  project's "Silver" medallion layer are being treated as the same thing here, on
  purpose, not by oversight) — one line in the file's own comments will say so.
- `macros/generate_schema_name.sql`: standard override so `+schema: silver` resolves
  to exactly `novalake.silver` rather than dbt's default `<target_schema>_<custom>`
  concatenation. Needed now, not a later cleanup — gets the schema convention right
  from the first model.
- `models/staging/_sources.yml`: declares `source('bronze', 'raw_events')` against
  `database: novalake`, `schema: bronze` — the dbt-side pointer to what
  `src/ingest.py` writes.
- `models/staging/stg_raw_events.sql`: thin pass-through `select` off that source —
  proves the Bronze→dbt read path works, nothing more (no flattening/drift-fixing
  here; that's the real Silver work for next time).
- `models/staging/_staging.yml`: `not_null` on `event_id`/`event_type`,
  `accepted_values` on `schema_version` (`1.0`/`2.0`) — small, real tests that
  exercise dbt's test framework against genuinely drifting data.

### `dbt_profiles/profiles.yml` (new)
`env_var()`-based `novalake` profile (`dev`/`prod` targets), `type: databricks`,
`catalog: novalake`, `schema: silver`, `host`/`http_path`/`token` from
`DATABRICKS_HOST` / `DATABRICKS_HTTP_PATH` / `DATABRICKS_TOKEN`. This is for local
`dbt run`/`dbt test` only — the DAB `dbt_task` in the job doesn't need
`profiles_directory`; Databricks Jobs auto-manages dbt auth against the job's SQL
warehouse.

### `resources/dbt_job.yml` (new)
One job, two tasks, plus a job-level `environments` block (serverless
`spark_python_task` needs an explicit `environment_key` — omitting a cluster block
is necessary but not sufficient on its own; Opus review flagged this as the highest
deploy-risk item):
1. `bronze_ingest` — `spark_python_task` → `../src/ingest.py`,
   `--catalog ${var.catalog}`, `environment_key: default_env` (job-level
   `environments: [{environment_key: default_env, spec: {client: "4"}}]`).
2. `dbt_silver_gold` — `depends_on: bronze_ingest`, `dbt_task` →
   `project_directory: ../src/dbt`, `commands: [dbt run, dbt test]` (no `dbt deps`
   — no `packages.yml` exists yet, so it would be a no-op; add it back if/when a
   package is actually used), `catalog: ${var.catalog}`, `schema: silver`,
   `warehouse_id: ${var.warehouse_id}`.
   Not setting `profiles_directory` — a job-managed `dbt_task` auto-generates
   Databricks auth for dbt, so it shouldn't be needed. Flagged as a
   verify-at-`bundle validate`-time assumption, not asserted as settled, since it
   depends on Databricks' auto-generated profile name lining up with
   `profile: novalake` in `dbt_project.yml`.

### `databricks.yml` (new)
`bundle.name: novalake`, `include: [resources/*.yml]`, `variables.catalog` (default
`novalake`), `variables.warehouse_id` (placeholder — needs the real Free Edition SQL
warehouse **ID** (the hex id from `databricks warehouses list`, not the display
name) filled in before first deploy, flagged inline as a TODO comment, matching how
`docs/00-setup.md` already flags Free-Edition-specific manual steps).
`targets.dev` only (default, `mode: development`) — no `prod` target yet, per the
user's decision above; `profile: DEFAULT` as a placeholder the user confirms/adjusts
against their actual `~/.databrickscfg` profile name.

### `requirements-dbt.txt` (new)
`dbt-databricks>=1.8,<2.0` — local dev only (the job's dbt_task runs its own
managed environment; this file is for running `dbt` from a laptop).

### `.gitignore` (edit)
Add `src/dbt/target/`, `src/dbt/dbt_packages/`, `src/dbt/logs/` under a new "dbt"
section — scoped to the dbt project path, not bare top-level patterns (a bare
`logs/` would ignore any future top-level logs directory unrelated to dbt).

### `README.md` (edit)
- Architecture section (lines ~3-6 prose): update "orchestration (Jobs, then
  Declarative Pipelines)" — orchestration is DAB-wrapped from `v0.1` onward (not
  deferred), Silver/Gold are dbt models; Declarative Pipelines moves to a later
  comparative-learning phase rather than being the primary Silver/Gold path.
- `Status` line (currently `🚧 v0.0 in progress`): update to reflect the pivot has
  landed structurally (still in-progress on content, but the scaffold now matches
  the new plan) — exact wording decided at edit time based on what's actually true
  once the files exist.
- Roadmap table condensed to match the pivot, with Declarative Pipelines kept as an
  explicit later phase (deferred, not dropped) rather than silently disappearing:

  | Tag | Phase | What it builds |
  |-----|-------|-----------------|
  | `v0.0` | Setup | Catalog, schemas, volume |
  | `v0.1` | Bronze | `src/ingest.py` PySpark ingest, wrapped in a DAB job resource |
  | `v0.2` | Silver | dbt models + tests: explode/flatten, drift reconciliation, dedupe, DLQ |
  | `v0.3` | Gold | dbt models: business metrics, conformed dimensions |
  | `v0.4` | Serving | Genie space on Gold, dashboard/feature tables |
  | `v0.5` | CI/CD | GitHub Actions, service-principal deploy, `bundle validate` gate, `prod` target |
  | `v0.6` | GenAI | Vector Search + Agent Bricks support-assist RAG, text-to-SQL |
  | `v0.7` | Declarative Pipelines (compare) | Re-implement part of Gold with Lakeflow Declarative Pipelines, now that the dbt path is understood — a second learning exercise, not a replacement |

- Repo structure block updated to the tree above.

### `docs/checkpoint.md` (edit)
Do not delete the original reasoning — but do more than append, since the header
matter itself now self-contradicts the new plan:
- Update the `Status` / `Re-open at` header line (currently "re-open at start of
  `v0.5` (Lakeflow Jobs), decide go/no-go at `v0.6` (Declarative Pipelines)") —
  those phases no longer exist under the new roadmap, so this line must be updated
  to point at the new phase numbering, not left dangling.
- Add a "Revised decision" section recording **both** reversals explicitly, not
  just the DAB-timing one:
  1. DAB adopted from `v0.1` onward, not deferred to `v0.5` — because the workflow
     now under construction (PySpark/dbt/Genie/DAB) treats the bundle as part of
     the architecture from day one rather than an add-on. Hand-authoring
     `databricks.yml`/`resources/dbt_job.yml` directly (no agent-authored IaC, per
     the untouched agentic-integration principle) still satisfies the original
     "understand it by hand before automating" intent — only the *timing* changed,
     not that principle.
  2. dbt adopted as the primary Silver→Gold path, **replacing** Declarative
     Pipelines in that role — because SQL models + tests better fit the "SDLC
     layer" goal (version-controlled, tested, environment-aware). Declarative
     Pipelines is not dropped from the project's scope — it's deferred to a later
     comparative-learning phase (`v0.7`), consistent with this repo's own pattern
     of understanding one abstraction before adopting the next.
- Append the dated entry to the "Revisit log" table (2026-07-16).

### `docs/01-bronze.md` (edit)
Add one changelog line + a short pointer near §7 noting `src/ingest.py` is now the
job-driven counterpart to the notebook, and the module's original notebook stays as
the historical validated record.

### `CONTRIBUTING.md` (edit)
Update the Definition-of-Done bullet listing where logic lives to include `src/`
and `resources/` (already-existing bullet just needs the new paths folded in), and
note dbt's own test framework counts toward "validation checklist is green" where a
module's logic lives in dbt models.

## Verification
- `find` / read back the new tree to confirm structure matches.
- Ask user for their actual SQL warehouse **ID** and `~/.databrickscfg` profile
  name to fill the two placeholders in `databricks.yml` (I won't read
  `~/.databrickscfg` directly — that was already declined once this session).
- Once placeholders are filled, run `databricks bundle validate` and treat it as a
  real check, not a formality — specifically confirm the `environments`/
  `environment_key` wiring on `bronze_ingest` and the `dbt_task` serverless syntax
  are actually accepted (these were the two items Opus's review flagged as
  asserted-but-unverified). Fix and re-validate if it rejects either.
- If the user wants, also run `dbt debug` / `dbt run --select stg_raw_events`
  locally (needs `DATABRICKS_HOST`/`DATABRICKS_HTTP_PATH`/`DATABRICKS_TOKEN` env
  vars set) to confirm the wiring works end-to-end, not just that the YAML parses.
- No deploy (`databricks bundle deploy`) without explicit user go-ahead, per the
  standing risky-action policy.

## Execution outcome (2026-07-16)

Executed as written, with one correction found by `databricks bundle validate`
that the plan itself had flagged as an unverified assumption: the `dbt_task` also
requires its own `environment_key` on serverless compute, not just the
`spark_python_task` — added, and `bundle validate -t dev` now passes cleanly.
Warehouse ID (`8fd481cbf45ac93e`) and CLI profile (`DEFAULT`) were confirmed via
the Databricks MCP tools and `databricks auth profiles` rather than by reading
`~/.databrickscfg` directly. See `docs/adr/` for the formal decision records this
plan produced, and `docs/checkpoint.md` for the narrative ADR this plan revises.

**Local dbt run (2026-07-16):** `dbt debug`/`run`/`test` all passed against the
real warehouse. Found and fixed along the way: `auth_type: oauth` (not
`databricks-cli` — dbt-databricks doesn't accept that literal, but reuses the
same CLI token cache), and a deprecated `accepted_values` test-argument shape.
`bronze_rows == silver_rows` (7105 == 7105).

**Real DAB job run (2026-07-16):** `databricks bundle deploy` + `bundle run
novalake_medallion` — first attempt failed: `dbt_silver_gold` hit exit 127
("command not found"). The job-managed `dbt_task` auto-generates auth as
assumed (that part was never the problem), but serverless environments don't
ship `dbt` preinstalled — needed `dbt-databricks` declared explicitly under the
task's `environment_key`. Split into a dedicated `dbt_env` (separate from
`bronze_ingest`'s `pyspark_env`), redeployed, reran: `TERMINATED SUCCESS`,
`bronze_ingest` wrote 7105 rows, `dbt_silver_gold` completed (dbt exits non-zero
on test failure, so this confirms all 3 tests too). Row counts reconfirmed equal
post-run. This closes the last open assumption from ADR-0004.
