# DAB and dbt, explained (for someone who already knows Databricks, PySpark, and SQL)

This note is my own reference. It assumes I'm fluent in Databricks, PySpark, and
SQL, and that I've never used Databricks Asset Bundles (DAB) or dbt before this
session. It walks through what those two tools actually are, every file the
NovaLake pivot added or changed, how to see the results in the workspace UI, and
— the part worth re-reading — the three bugs that only showed up when things were
run for real.

If you want the decisions rather than the mechanics, read `docs/checkpoint.md`
and `docs/adr/`. This note is the "how does this actually work" companion to
those.

---

## 1. What Databricks Asset Bundles (DAB) actually is

DAB is infrastructure-as-code for Databricks. Instead of clicking through the
Workflows UI to create a job, wiring tasks together, and picking compute, you
describe all of that in YAML files in the repo, and `databricks bundle deploy`
turns that YAML into real workspace objects (jobs, pipelines, etc.). The objects
it creates are exactly the same kind you'd get from the UI — a bundle-deployed
job shows up in the same Jobs list, runs the same way. The difference is where
the definition lives: in version-controlled, reviewable text instead of in
someone's click history.

The mental model that made it click for me: **DAB is to a Databricks Job what a
Dockerfile is to a running container, or what Terraform is to cloud infra.** The
YAML is the source of truth; the workspace object is a build artifact of it.

Why this matters beyond "now there are more files to maintain":

- **Reproducibility.** The job can be destroyed and recreated identically from
  the repo. No "who changed the cluster config in the UI and didn't tell anyone."
- **Code review on infrastructure.** A change to how the job runs is a diff in
  `resources/dbt_job.yml` that goes through a PR, same as application code.
- **Multi-environment deploys.** DAB's `-t` flag is how a bundle *can* deploy to
  different targets with different names/paths/identities in general. NovaLake
  deliberately never uses that beyond `dev`, though — one Free Edition
  workspace means a same-workspace `prod` would only be a semantic overlay, not
  real environment isolation. See [ADR-0007](../adr/0007-defer-prod-no-same-workspace-production-semantics.md)
  and [ADR-0008](../adr/0008-novalake-terminus-and-cerberus-succession.md).
- **CI/CD readiness.** `databricks bundle validate` is a real schema/consistency
  check you can run in GitHub Actions on every PR before anything deploys. It's
  the gate that turns "the YAML probably parses" into "the YAML is provably
  well-formed."

The commands I actually used this session:

- `databricks bundle validate` — static check: does the YAML conform to the
  bundle schema, do task references resolve, are required fields present. Fast,
  no workspace mutation.
- `databricks bundle deploy` — uploads the bundle's files to the workspace and
  creates/updates the job. Targets `dev` by default (no `-t` needed) because
  `dev` is `default: true`.
- `databricks bundle run novalake_medallion` — triggers the deployed job and
  streams its run.
- `databricks bundle summary` — prints what the bundle deployed: the job's
  workspace URL, the target, the resolved variable values. The fastest way to
  jump from the CLI to the right page in the UI.

---

## 2. What dbt actually is

dbt is a SQL build tool plus a test framework. It runs **against a warehouse**
(here, a Databricks SQL warehouse) — it is not Spark, does not use a Spark
cluster, and does not process data itself. It compiles your SQL and sends it to
the warehouse to execute. Think of dbt as the thing that manages *your SQL as a
software project* rather than as a pile of notebook cells.

Two concepts carry most of dbt's value:

1. **`ref()` / `source()` and the dependency graph.** Instead of hardcoding
   `novalake.bronze.raw_events` in a query, you write
   `{{ source('bronze', 'raw_events') }}`; instead of hardcoding another model's
   table name, you write `{{ ref('stg_raw_events') }}`. dbt reads all of these,
   builds a DAG of what depends on what, and runs models in dependency order.
   That DAG is what powers `dbt run --select stg_raw_events+` (run this model and
   everything downstream of it) and automatic lineage. You never manage run order
   by hand.

2. **Tests as SQL.** A dbt test is a query that's expected to return **zero
   rows** — if it returns any rows, the test fails. The built-in generic tests
   (`not_null`, `unique`, `accepted_values`, `relationships`) are just
   parameterized versions of that. You declare them in YAML next to the model.

Why this is genuinely different from "just writing SQL in a notebook," even
though the SQL itself looks the same:

- **Version control and review** — models are files, changes are diffs.
- **Tests live with the model** and run on every `dbt test`, so a schema
  assumption ("`schema_version` is always `1.0` or `2.0`") is enforced, not just
  hoped for.
- **Environment awareness** — the same model deploys to different
  catalogs/schemas by swapping the profile target, no SQL edits.
- **The `ref()` graph** gives you ordering, lineage, and selective runs for
  free. A notebook gives you none of that; you order cells by hand and hope.

The commands: `dbt debug` (can I connect?), `dbt run` (build the models),
`dbt test` (run the tests). dbt exits non-zero if a test fails — which is why a
green job run also proves the tests passed.

---

## 3. Every file the pivot added or changed, and why

### `src/ingest.py` — PySpark Bronze ingest

A faithful port of the original hand-run notebook
(`notebooks/01_bronze/01_bronze_raw_event_ingestion.ipynb`, left in place as the
historical v0.1 record) into a plain script that a DAB `spark_python_task` can
run. It takes `--catalog` via `argparse` (so the job passes it as a parameter
instead of a notebook widget), reads
`/Volumes/{catalog}/bronze/landing/payments_events.json`, adds `_source_file`
(from `_metadata.file_path`) and `_ingested_at` (`current_timestamp()`), and
writes `mode("overwrite")` + `overwriteSchema=true` to
`{catalog}.bronze.raw_events`. Same schema-on-read, no-restructuring behavior as
the notebook — cleanup is Silver's (now dbt's) job.

Note the comment block where a `.cache()` used to be — see the debugging section;
serverless doesn't allow it, and the trailing `count()` re-reads the source
instead. It's a real but negligible cost at ~7K rows.

### `src/dbt/dbt_project.yml` — the dbt project root

Declares `profile: novalake` (which profile in `profiles.yml` to use),
`require-dbt-version: [">=1.8.0", "<2.0.0"]` (pinned to match
`requirements-dbt.txt` so local and job dbt can't drift), and the models config:
everything under `staging/` materializes as a **view** in schema **silver**.
The comment in the file records the deliberate choice that dbt's "staging"
convention and the project's "Silver" medallion layer are the same thing here,
on purpose.

### `src/dbt/macros/generate_schema_name.sql` — schema-name override

This one is non-obvious and worth understanding. dbt's **default**
`generate_schema_name` macro concatenates the target schema with a model's
`+schema` config: target `silver` + `+schema: gold` would land the table in
`silver_gold`, not `gold`. That breaks NovaLake's `novalake.<layer>.<object>`
convention immediately. The override makes `+schema: silver` resolve to exactly
`novalake.silver` — no concatenation:

```sql
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
```

Full reasoning in ADR-0005. The tradeoff: you lose dbt's default per-target
sandbox-schema isolation, which is fine for a solo project sharing one workspace.

### `src/dbt/models/staging/stg_raw_events.sql` — the one model

A thin pass-through `SELECT` off `{{ source('bronze', 'raw_events') }}`. It
deliberately does **not** do the real Silver work (exploding arrays, reconciling
`1.0`/`2.0` drift, collapsing the struct-vs-string `payload.risk` field,
deduping replayed IDs). Its entire job is to prove the Bronze→dbt read path works
end to end. Real Silver modeling is a later pass.

### `src/dbt/models/staging/_sources.yml` — the Bronze pointer

Declares the `bronze` source with `schema: bronze`. Notably it does **not**
hardcode `database: novalake` — it lets that default to `target.database`, which
tracks the same `catalog` bundle variable everything else uses. Hardcoding it
would silently decouple the source from that variable if it's ever overridden
(this was actually a review fix — see below).

### `src/dbt/models/staging/_staging.yml` — the tests

Three tests: `not_null` on `event_id` and `event_type`, `accepted_values` on
`schema_version` (`["1.0", "2.0"]`). The deliberate omission is the important
part: **no `unique` test on `event_id`**, because ~1.5% of event IDs are
intentionally replayed in the synthetic dataset by design. A naive uniqueness
test would be a false positive that flags the data as broken when it's behaving
exactly as intended. The YAML uses the `arguments:` nesting shape that this
dbt-core version requires for `accepted_values` (also found the hard way).

### `databricks.yml` — the bundle root

Declares `bundle.name: novalake`, includes `resources/*.yml`, and defines two
variables: `catalog` (default `novalake`) and `warehouse_id`. `warehouse_id`
uses a `lookup:` by name (`"Serverless Starter Warehouse"`) rather than a
hardcoded hex ID — so it survives the warehouse being recreated, which happens on
Free Edition. One target, `dev` (default) — `mode: development` was removed
during `v0.4` (its automatic `[dev <user>] ` name prefix broke deploying an
already-existing dashboard in place; the two presets that actually mattered
were kept explicitly instead), and `workspace.profile` was removed during
`v0.5` (`dev` is now deployed by two different identities — Chirag locally,
`novalake-cicd` in CI — so the target can't hardcode a personal profile; run
locally with `-p DEFAULT`). No `prod` target, permanently — not just "not yet."
See [ADR-0007](../adr/0007-defer-prod-no-same-workspace-production-semantics.md).

### `resources/dbt_job.yml` — the job

One job, `novalake_medallion`, two tasks:

1. `bronze_ingest` — `spark_python_task` → `src/ingest.py`, passing
   `--catalog ${var.catalog}`. Uses `environment_key: pyspark_env`.
2. `dbt_silver_gold` — `dbt_task` → `src/dbt`, running `dbt run` then `dbt test`,
   with `catalog`, `schema: silver`, and `warehouse_id` set. `depends_on:
   bronze_ingest`. Uses `environment_key: dbt_env`.

The `environments` block at the bottom is the load-bearing part on serverless:
two separate environments, `pyspark_env` (bare, `client: "4"`) and `dbt_env`
(same, plus `dependencies: ["dbt-databricks>=1.8,<2.0"]`). The split exists
because of bug #3 below — serverless doesn't ship dbt, and only the dbt task
should carry that dependency.

### `dbt_profiles/profiles.yml` + `requirements-dbt.txt` — local dbt dev

These are for the **local** dev loop, deliberately separate from the job's
`dbt_task`. `profiles.yml` defines the `novalake` profile: `type: databricks`,
`catalog: novalake`, `schema: silver`, `host`/`http_path` from env vars, and
crucially `auth_type: oauth` with **no static token** — it reuses the CLI's own
OAuth token cache (`~/.databricks/token-cache.json`). `requirements-dbt.txt`
pins `dbt-databricks>=1.8,<2.0`. The reasoning (ADR-0004): dbt's whole value is a
fast local edit→run→test loop; routing every model change through a full cloud
job deploy would defeat it. The job task is for orchestrated/scheduled runs, not
primary development.

### `docs/architecture.md` — the diagrams

Two Mermaid diagrams: the medallion data flow (which tool owns each layer) and
the actual DAB job graph. Mermaid specifically because GitHub renders it natively
in markdown — no external diagramming tool, stays version-controlled as text.

### `docs/adr/` — five decision records

Nygard-style (Context / Decision / Consequences / Alternatives), one per genuine
decision: 0001 DAB-from-v0.1, 0002 dbt-replaces-Declarative-Pipelines (deferred,
not dropped), 0003 dev-only bundle target, 0004 local dbt workflow, 0005 the
schema-name macro. `docs/checkpoint.md` (the original pinned "DAB later"
decision) got a "Revised decision" section recording the reversal and why, with
the original reasoning left intact — treated as a living document, not
overwritten.

---

## 4. Seeing the results in the Databricks workspace UI

After `databricks bundle deploy` + `databricks bundle run`, here's where the
output actually lives. `databricks bundle summary` prints direct links to most of
this.

**Workflows / Jobs.** Left nav → **Workflows** → **Jobs** tab. The job appears
as `[dev] novalake bronze-to-silver` — just the one prefix, from the configured
name `[${bundle.target}] novalake bronze-to-silver`. (Earlier in `v0.4` this
briefly showed up double-prefixed, `[dev <username>] [dev] ...` — `mode:
development`'s automatic name prefix stacking with this one. That's why `mode:
development` was removed from `databricks.yml`'s `dev` target; see the
`databricks.yml` section above.) Open it to see the two-task
graph (`bronze_ingest` → `dbt_silver_gold`), the run history, and — click into a
run, then a task — the driver logs (stdout/stderr). This is where `Wrote 7105
rows...` and the `dbt run`/`dbt test` output show up.

**Catalog Explorer.** Left nav → **Catalog** → `novalake`. Under the `bronze`
schema you'll find `raw_events` (written by `bronze_ingest`); under `silver`,
`stg_raw_events` (the dbt view). Clicking a table shows its schema, sample data,
and lineage.

**Workspace file browser.** The bundle uploads its files to
`/Workspace/Users/chiragvenkatesh92@gmail.com/.bundle/novalake/dev/files/`. This
is the deployed copy of `src/`, `resources/`, etc. that the job actually runs —
useful for confirming what got deployed matches the repo. (Editing here is a
mistake; the repo + `bundle deploy` is the source of truth.)

**Compute → SQL Warehouses.** Left nav → **Compute** → **SQL Warehouses** →
`Serverless Starter Warehouse`. This is the warehouse the dbt task and local dbt
both run against (the one `warehouse_id` looks up by name).

---

## 5. The three bugs that only surfaced by running things for real

This is the part of the session worth remembering. Static validation caught one
of these. The other two were only found by actually executing against the real
platform. This is the whole argument for verification over reasoning.

### Bug 1 — `dbt_task` also needs its own `environment_key` (caught by `bundle validate`)

The first draft put an `environment_key` on the `spark_python_task` but assumed
the `dbt_task` didn't need one. `databricks bundle validate` — a pure
schema/consistency check, no deploy — rejected it: on serverless, the `dbt_task`
requires an `environment_key` too. Added it, re-validated clean. Cheap bug, found
by the cheapest check. Worth noting the Opus plan-review pass had *already*
flagged that serverless `spark_python_task` needs an explicit
`environments`/`environment_key` block at all (the original plan wrongly asserted
it needed no compute config) — so the class of bug was predicted before writing;
validate just found the exact instance.

### Bug 2 — dbt auth type and a deprecated test-arg shape (caught by running local dbt)

Running the actual local loop — `dbt debug` / `dbt run` / `dbt test` against the
real warehouse, not just eyeballing the YAML — surfaced two things:

- `databricks auth describe` reports the profile's auth type as the literal
  string `databricks-cli`. dbt-databricks does **not** accept that literal —
  `dbt debug` failed until the profile said `auth_type: oauth`. Critically,
  `oauth` reuses the *same* cached token file
  (`~/.databricks/token-cache.json`), so no new browser login and no PAT had to
  be generated or stored anywhere. Same credentials, different accepted spelling.
- The `accepted_values` test needed its args nested under `arguments:` in this
  dbt-core version — the older flat shape is deprecated.

After fixing: `dbt run` built `novalake.silver.stg_raw_events`, all three tests
passed, and a manual count confirmed `bronze_rows == silver_rows` (7105 == 7105)
— no silent data loss in the pass-through.

### Bug 3 — serverless doesn't ship dbt (caught only by a real `bundle run`)

The first real end-to-end job run — `databricks bundle deploy` + `databricks
bundle run novalake_medallion` — **failed**. `dbt_silver_gold` exited with code
**127** ("command not found").

Root cause: it's easy to assume that because a job-managed `dbt_task`
auto-generates its Databricks auth, everything "just works." The auth assumption
was actually correct — that was never the problem. What's *not* provided is `dbt`
itself: serverless compute environments don't ship it preinstalled. `dbt` has to
be declared explicitly as a pip dependency under the environment's
`spec.dependencies`.

The fix was to split what had been one shared environment into two scoped ones:
`pyspark_env` for the PySpark task (no dbt dependency — it doesn't need it) and
`dbt_env` for the dbt task, with `dbt-databricks>=1.8,<2.0` declared. Redeployed,
reran: `TERMINATED SUCCESS`. `bronze_ingest` wrote 7105 rows, `dbt_silver_gold`
completed — and because dbt exits non-zero on a test failure, a clean completion
also confirms all three tests passed. Row counts reconfirmed equal.

Note the workflow discipline around this: PR #1 was opened as a **draft** on
purpose, specifically because the job run hadn't been verified yet, and only
marked ready-for-review after this run went green. That mirrors CONTRIBUTING.md's
Definition-of-Done — a green validation checklist before merge, not just "the
YAML parses."

### The bonus lesson — a confidently-wrong review "fix" (`.cache()`)

Before merge, an 8-agent parallel review found six real issues that got fixed (a
stale `default_env` reference in the architecture diagram after the env split; a
hardcoded `database: novalake` that only worked by coincidence with the variable
default; a self-contradiction in `plan.md`'s repo tree; a checkpoint section that
read as still-current in isolation; the hardcoded `warehouse_id` that became the
`lookup:` pattern).

But one suggested fix was **wrong** and caused a regression. Adding `.cache()` to
`src/ingest.py` — to avoid the redundant source read before the trailing
`count()` — is textbook-idiomatic PySpark efficiency advice. The very next real
job run failed immediately: `NOT_SUPPORTED_WITH_SERVERLESS: PERSIST TABLE is not
supported on serverless compute`. Databricks serverless (Spark Connect under the
hood) doesn't support `.cache()` / `.persist()` at all. It was caught only
because the fix was re-verified by re-running the job, not by trusting the
review's reasoning. Reverted immediately; the minor double-read is accepted as
negligible at ~7K rows. A review agent applying general best practices without
knowing this specific platform's serverless limitation produced confidently-wrong
advice — and only a real run caught it.

That's the through-line of the whole session: **validate catches schema bugs,
local runs catch integration bugs, and only real end-to-end runs catch
platform-specific behavior — for AI-suggested code and hand-written code
alike.**

---

## 6. Quick reference

| I want to... | Command |
|---|---|
| Check the bundle YAML is well-formed | `databricks bundle validate` |
| Create/update the job in the workspace | `databricks bundle deploy` (targets `dev`) |
| Run the deployed job | `databricks bundle run novalake_medallion` |
| See what deployed + get the job URL | `databricks bundle summary` |
| Iterate on a model fast (local) | `dbt run --select stg_raw_events` then `dbt test` |
| Confirm dbt can connect | `dbt debug` |

Local dbt needs `DATABRICKS_HOST` and `DATABRICKS_HTTP_PATH` env vars pointed at
the Serverless Starter Warehouse; auth flows through the CLI's own OAuth token
cache, so there's no token to set.
