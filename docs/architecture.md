# Architecture

Two diagrams: the medallion data flow (what tool owns each layer), and the
Databricks Asset Bundle (DAB) orchestration graph (how the job actually runs).
See `docs/checkpoint.md` and `docs/adr/` for the decisions behind this shape.

## 1. Data flow

```mermaid
flowchart LR
    subgraph Raw["Raw · Unity Catalog Volume"]
        A["payments_events.json<br/>NDJSON"]
        B["payments_events_multiline.json<br/>nested API export"]
    end

    subgraph Bronze["Bronze · PySpark (src/ingest.py)"]
        C[("novalake.bronze.raw_events")]
    end

    subgraph SilverGold["Silver / Gold · dbt (src/dbt/)"]
        D[("novalake.silver.*")]
        E[("novalake.gold.*")]
    end

    subgraph Serving["Serving"]
        F["Genie space<br/>NL analytics"]
        H["Dashboards / feature tables"]
    end

    G["GenAI layer<br/>Vector Search + Agent Bricks (v0.6)"]

    A --> C
    B -.not yet ingested.-> C
    C -->|"dbt source()"| D --> E
    E --> F
    E --> H
    F --> G
```

**Per-layer ownership:**

| Layer | Tool | Where | Why this tool |
|-------|------|-------|----------------|
| Bronze | PySpark | `src/ingest.py` | Genuinely messy nested/polymorphic JSON — schema inference, `from_json`, explode/quarantine logic is where Spark earns its place; dbt can't touch raw JSON like this. |
| Silver / Gold | dbt | `src/dbt/models/` | SQL models + tests — version-controlled, environment-aware, the project's SDLC layer. Replaces the originally-planned Lakeflow Declarative Pipelines for this role (see [ADR-0002](adr/0002-use-dbt-for-silver-gold.md)). |
| Serving | Genie | Databricks workspace (Genie space over Gold) | Natural-language analytics for anyone who doesn't want to write SQL against Gold. |
| Orchestration | DAB | `databricks.yml`, `resources/*.yml` | Deploys and wires Bronze → Silver/Gold as one job, from `v0.1` onward (see [ADR-0001](adr/0001-adopt-dab-from-v0.1.md)). |

## 2. DAB job graph

What `databricks bundle deploy` actually creates, per `resources/dbt_job.yml`:

```mermaid
flowchart TB
    subgraph Bundle["databricks.yml — bundle: novalake, target: dev"]
        subgraph Job["Job: novalake_medallion"]
            T1["Task: bronze_ingest<br/>spark_python_task → src/ingest.py<br/>environment_key: pyspark_env (serverless)"]
            T2["Task: dbt_silver_gold<br/>dbt_task → src/dbt (dbt run, dbt test)<br/>environment_key: dbt_env (serverless, dbt-databricks dependency)<br/>depends_on: bronze_ingest"]
            T1 --> T2
        end
    end
```

**Two ways `src/dbt/` actually gets run**, and they're deliberately different loops:

```mermaid
flowchart LR
    Dev["Local dbt dev<br/>dbt_profiles/profiles.yml + env vars<br/>dbt run / dbt test (fast iteration)"] --> Models[("src/dbt/models")]
    Job["DAB job task: dbt_silver_gold<br/>Databricks-managed auth, no profiles_directory"] --> Models
    Models --> UC[("Unity Catalog<br/>novalake.silver / novalake.gold")]
```

Local dbt (`requirements-dbt.txt`) is for day-to-day model development — the fast
loop dbt is built for. The DAB `dbt_task` is for orchestrated/scheduled runs, not
primary development; see [ADR-0004](adr/0004-local-dbt-development-workflow.md).

## Targets

Only `dev` exists today (`databricks.yml`). `prod` is intentionally not
pre-scaffolded — it arrives at `v0.5` (CI/CD) alongside the service-principal
deploy it actually requires. See [ADR-0003](adr/0003-dev-only-bundle-target.md).
