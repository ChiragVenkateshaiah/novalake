# NovaLake

A hands-on Databricks lakehouse build, end to end: raw event data → Bronze (PySpark)
→ Silver → Gold (dbt) → Serving (Genie) → a GenAI layer on top of the same curated
data — orchestrated by a Databricks Asset Bundle (DAB) from the first phase onward,
deployed via CLI now and CI/service-principal later. Lakeflow Declarative Pipelines
is a later, comparative learning phase (`v0.7`), not the primary Silver/Gold path —
see `docs/checkpoint.md` for why. Built on **Databricks Free Edition**, documented
as it's built, every transformation and decision versioned in this repo.

NovaLake is the analytical/AI counterpart to **[NovaPay](#)** (a separate
production-style payments platform project) — NovaPay generates the operational
event stream; NovaLake is the lakehouse that turns it into business metrics, served
dashboards, and a support-assist AI agent.

## Why this exists

A structured way to go deep on Databricks: not tutorials, a real (synthetic) messy
dataset, transformed by hand through every layer before any orchestration or
automation is introduced — so each abstraction is understood before it's adopted.
See [`docs/checkpoint.md`](docs/checkpoint.md) for the explicit decision on *when*
agentic tooling (Claude Code + Databricks MCP) enters this build.

## Architecture

```mermaid
flowchart LR
    subgraph Raw["Raw · Unity Catalog Volume"]
        A["payments_events.json<br/>NDJSON"]
        B["payments_events_multiline.json<br/>nested API export"]
    end
    subgraph Lakehouse
        C[("Bronze<br/>PySpark · src/ingest.py")]
        D[("Silver<br/>dbt · src/dbt/")]
        E[("Gold<br/>dbt · src/dbt/")]
        F[("Serving<br/>Genie + dashboards")]
    end
    G["GenAI layer<br/>Vector Search + Agent Bricks"]

    A --> C
    B -.not yet ingested.-> C
    C --> D --> E --> F
    F --> G
```

Bronze → Silver/Gold → Serving is orchestrated as one Databricks Asset Bundle job
from `v0.1` onward (`databricks.yml`, `resources/dbt_job.yml`). See
[`docs/architecture.md`](docs/architecture.md) for the DAB job graph and the
local-dev-vs-orchestrated-run split, and [`docs/adr/`](docs/adr/) for the decision
records behind this shape.

## Roadmap

| Tag | Phase | What it builds | Learn |
|-----|-------|-----------------|-------|
| `v0.0` | Setup | Catalog, schemas, volume, Git folder | Workspace, Unity Catalog basics |
| `v0.1` | Bronze | `src/ingest.py` PySpark ingest, wrapped in a DAB job resource | Ingestion, schema-on-read, DAB from day one |
| `v0.2` | Silver | dbt models + tests: explode/flatten, drift reconciliation, dedupe, DLQ | Real PySpark/SQL transformation, dbt |
| `v0.3` | Gold | dbt models: business metrics, conformed dimensions | Aggregation, dimensional modeling |
| `v0.4` | Serving | Genie space on Gold, dashboard/feature tables | Serving patterns, AI/BI |
| `v0.5` | CI/CD | GitHub Actions, service-principal deploy to `dev`, `bundle validate` PR gate | Continuous deployment |
| `v0.6` | GenAI | Vector Search + Agent Bricks support-assist RAG, text-to-SQL | RAG, agents, eval |
| `v0.7` | Declarative Pipelines (compare) | Re-implement part of Gold with Lakeflow Declarative Pipelines | Declarative ETL, DQ-as-code, vs. dbt |
| `v0.8` | *Reserved* | Not yet scoped — see [ADR-0008](docs/adr/0008-novalake-terminus-and-cerberus-succession.md) | — |
| `v0.9` | Spark optimization (final phase) | Query profiles, `EXPLAIN`, liquid clustering, `OPTIMIZE`, join/skew tuning — within serverless's constraints, on GB-scale regenerated data | Spark optimization NovaLake's compute model can actually expose |
| — | Cross-cutting | Unity Catalog governance, observability | Continuous, from `v0.1` onward |

Each tag = a tagged GitHub release: the table/asset works, the logic is committed,
the doc module is filled, and the validation checklist is green.

**`v0.9` is NovaLake's terminus** — there is no `v0.10`. Serverless compute
structurally can't expose infra-level Spark tuning (no Spark UI, no cluster
sizing, most `spark.conf` locked) or real dev/prod environment isolation
(one Free Edition workspace). Rather than fake either inside NovaLake, both
succeed to a new project, **Cerberus** — AWS, Terraform-first IaC, classic/
self-managed Spark compute, with NovaPay (the companion payments app) as
its upstream data producer. See
[ADR-0007](docs/adr/0007-defer-prod-no-same-workspace-production-semantics.md)
and [ADR-0008](docs/adr/0008-novalake-terminus-and-cerberus-succession.md)
for the full reasoning.

## Repo structure

```
novalake/
├── README.md
├── CONTRIBUTING.md
├── databricks.yml         # Asset Bundle root — dev target only, no prod (see ADR-0007)
├── resources/
│   └── dbt_job.yml        # bronze ingest task -> dbt_task (Silver/Gold)
├── src/
│   ├── ingest.py           # PySpark: land + flatten the raw JSON (Bronze)
│   └── dbt/                # dbt project: Silver/Gold models + tests
├── dbt_profiles/
│   └── profiles.yml       # env_var()-based, local dbt dev only
├── requirements-dbt.txt   # dbt-databricks pin, local dev only
├── data/
│   ├── generators/        # synthetic dataset generators (reproducible)
│   └── dictionaries/      # what's in the data + the deliberate challenges
├── notebooks/             # historical: the original hand-run v0.1 Bronze notebook
├── docs/
│   ├── checkpoint.md      # pinned process decisions (e.g. agentic integration timing)
│   ├── _skeleton.md        # reusable doc module template
│   └── 00-setup.md, ...    # one filled module per phase
├── pipelines/             # Lakeflow Declarative Pipeline source (from v0.7, comparative)
└── .github/workflows/     # CI (from v0.5, deploys via service principal)
```
`pipelines/` isn't created yet — added when `v0.7` starts, not pre-scaffolded.
`.github/workflows/` was added at `v0.5` (CI/CD), same principle. See
`docs/checkpoint.md` for the DAB/dbt timing decisions and why `pipelines/`
moved from `v0.6` to a later comparative phase.

## Status

✅ `v0.2` Silver complete and merged to `main`, tagged `v0.2` — all 10 event
types across both raw sources (dedupe, envelope + payload drift-fix, DLQ split,
array explode, dynamic-map reconstruction, cross-page dimension resolution, fx
normalization, reconciliation; see [`docs/02-silver.md`](docs/02-silver.md)).
81 dbt models, verified locally and via a real DAB job run.

✅ `v0.3` Gold complete and merged to `main`, tagged `v0.3` — 20 Gold models
(conformed `dim_date`/`dim_customers`/`dim_merchants`, 8 fact tables, 9 metric
rollups) on top of Silver, every fact's row count verified against its source
`_clean` models; see [`docs/03-gold.md`](docs/03-gold.md).

✅ `v0.4` Serving complete and merged to `main`, tagged `v0.4` — Genie space
("NovaLake Gold Analytics") and a 3-page/11-dataset AI/BI dashboard on
Gold, both deployed, validated live, and wired into the DAB bundle
(`resources/dashboard.yml`); see [`docs/04-serving.md`](docs/04-serving.md).

✅ `v0.5` CI/CD complete and merged to `main` ([PR #5](https://github.com/ChiragVenkateshaiah/novalake/pull/5))
— GitHub Actions (`bundle validate` PR gate, fail-safe `bundle deploy` on
merge) automating the existing `dev` deploy via the `novalake-cicd`
service principal (secret-based OAuth M2M — Free Edition doesn't expose
OIDC federation, see
[ADR-0006](docs/adr/0006-secret-based-service-principal-auth-for-cicd.md)).
No `prod` target — real production semantics are out of scope for this
single-workspace project; see
[ADR-0007](docs/adr/0007-defer-prod-no-same-workspace-production-semantics.md)
and [ADR-0008](docs/adr/0008-novalake-terminus-and-cerberus-succession.md)
(NovaLake's terminus at `v0.9`, succeeded by Cerberus).
`bundle-validate.yml` caught and fixed a real unpinned-`root_path` bug on
its first real run; `bundle-deploy.yml` ran for real on merge and
succeeded, deploying to the existing `dev` job/dashboard in place (verified
directly in the workspace UI, no parallel copies). See
[`docs/05-cicd.md`](docs/05-cicd.md).
