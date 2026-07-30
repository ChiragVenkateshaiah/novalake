<!--
MEDIUM METADATA — Part 2 of 8
Title:      Bronze, and the confidently wrong fix
Subtitle:   51 inferred leaf fields, two of them lying — and an audit tool whose own null filter silently never fired. (110 chars)
Cover:      ../poster/part-2-bronze.png
SEO title:  Bronze, and the confidently wrong fix (36)
SEO desc:   Spark schema inference collapses mixed-type fields to string. Building a drift audit that found two genuine collapses, and three it couldn't see. (147)
Tags:       Databricks, PySpark, Data Engineering, Data Quality, Apache Spark
Source:     docs/articles/novalake-full-story.md — lines 56-116, verbatim
-->

# Bronze, and the confidently wrong fix

### Where the schema tells you it's fine and isn't — plus the pivot that reversed a decision I'd pinned in writing specifically so it wouldn't get re-litigated

*Part 2 of 8 in **The platform is the only source of truth**, a build log of a Databricks lakehouse taken end to end on Free Edition.*
*← Previous: [The platform is the only source of truth](LINK-PART-1) · Next: [Silver and Gold](LINK-PART-3) →*

---

**Where we are.** [Part 1](LINK-PART-1) covered what NovaLake is — a Databricks lakehouse built end to end on Free Edition, raw events through Bronze, Silver, Gold, Serving and a GenAI layer, shipped as nine tagged releases — and the four-stage escalation that governed how much access the AI agent got at each phase. This part is the first layer of actual data, where the tooling starts telling you things that aren't true.

## The architecture, and where this part sits

The cover strip shows the six stages of the data plane. This part lights the first two: **SOURCES → BRONZE**.

Concretely, that's a four-hop path. Two Python generators emit synthetic payments events — one as newline-delimited JSON, one as a pretty-printed JSON array of paginated API export pages. Both write into `novalake.bronze.landing`, a **Unity Catalog Volume**, and the raw JSON stops there: it is never committed to git, so only the generators and their data dictionaries are version-controlled. `src/ingest.py` then reads the Volume with PySpark and writes Delta into `novalake.bronze.raw_events`.

Two architectural choices govern everything in this part.

**PySpark here, dbt later.** Bronze is the one layer where the input is genuinely nested, polymorphic and malformed — 3–4 levels of nesting, a field that's a struct 97% of the time and a bare string the rest. That's where Spark's DataFrame API earns its place over SQL. From Silver onward the work is set-based transformation, which is dbt's job. The boundary between those two tools is the boundary between this part and the next.

**Bronze enforces nothing.** No schema, no drops, no restructuring — add `_source_file` and `_ingested_at`, write Delta, stop. Every defect in the source survives into the table intact, on purpose, because a Bronze layer that cleans data destroys the evidence you need to know what was wrong with it.

That second choice is precisely why the schema inference below is load-bearing: if Bronze doesn't enforce a schema, Spark infers one, and what it infers is the first thing in this project that turned out to be lying.

---

## Bronze — where the schema tells you it's fine and isn't

The Bronze rule is simple: no schema enforcement, drop nothing, restructure nothing. Read the NDJSON, add `_source_file` from `_metadata.file_path` and `_ingested_at` from `current_timestamp()`, write Delta. `novalake.bronze.raw_events` landed **7,105 rows**, matching the source line count exactly, verified against a per-`(event_type, schema_version)` breakdown that summed to exactly 7,105.

Spark's schema inference produced **51 leaf fields** — `payload` alone spanning every event type's fields as nullable siblings. And then two of those leaves turned out to be lying.

The first thing worth knowing: `_corrupt_record` was **absent entirely** from the inferred schema. Zero syntactically broken lines. That's not the good news it looks like. Spark's PERMISSIVE mode and `_corrupt_record` protect you from *syntactic* corruption — a line that isn't valid JSON. This dataset's entire problem is *semantic* type drift: every record is perfectly valid JSON that disagrees with its neighbors about what type a field is. Permissive mode is structurally blind to that.

So I built a general-purpose schema-drift audit instead of hand-checking the fields I already knew were dirty. It recursively flattens the inferred schema to leaf fields, filters to `StringType` leaves (because Spark's inference *collapses* genuinely mixed-type fields to `StringType` — the string type is the tell), then classifies each leaf's actual values by shape via regex: `json_object`, `json_array`, `numeric`, `date_like`, `plain_text`, `null`. Any field with more than one shape gets flagged.

It found exactly two genuine multi-shape collapses:

| Field | Shape distribution |
|---|---|
| `event_timestamp` | date_like 4,521 / numeric 2,440 / null 144 |
| `payload.risk` | json_object 3,131 / plain_text 103 / null 3,871 |

Those two are not the same kind of problem, and conflating them is how you write a fix that silently destroys data:

- **`payload.risk` is a destructive collapse.** A 3% minority of malformed rows — `risk` delivered as a string instead of a struct — forced the 97% well-formed majority to lose its struct type too, because no single column type holds both a struct and a string. Spark fell back to string for the entire column. Recovering it needs `from_json` with an explicit schema.
- **`payload.amount_minor` is a non-destructive collapse.** Int versus string. Nothing is lost; `try_cast("long")` recovers it regardless of which shape a given row started in.

And then there are three kinds of drift the shape profiler *can't see at all*, which is the honest limitation of the tool I'd just built:

- **Key renaming** — `cust_id` in v1 versus `customer_id` in v2. Same concept, two names, both perfectly consistent within themselves. Fixed with `coalesce`.
- **Structural reshaping** — `source_system` is a flat string in v1; `source` is a three-field struct in v2. Not a rename. A different shape entirely, needing version-branched parsing.
- **Value-level dirtiness** — `payload.currency` mixing `"USD"`, `"usd"`, `" GBP"`. One consistent *shape*, genuinely inconsistent *values*. A shape profiler reports this as clean. You need a distinct-value count, not a shape profile.

That framing — five distinct Bronze→Silver problem categories, each with a different SQL construct as its fix — became the explicit scope of the Silver phase.

**The audit tool had bugs of its own, which is the part I'm most glad I wrote down.** Its null filter compared against the string `"null"` while the data contained `"Null"` — Python string comparison is case-sensitive, the filter silently didn't fire, and it produced **46 false positives**. I caught it only by sanity-checking the audit's output against the generator's known injected counts. A second one is still visible in the notebook: the `json_array` classification branch reuses the exact same regex as `json_object` (`^\{.*\}$`) instead of `^\[.*\]$`. It's dead code. `json_array` never matched anything, ever.

An audit tool that reports zero findings for a category can mean the category is clean, or it can mean the check is broken. From the outside those look identical.

---

## The pivot, and the confidently wrong fix

Partway through Bronze I reversed a decision I'd deliberately pinned in writing months earlier specifically so it *wouldn't* get re-litigated by accident.

The original roadmap: hand-written notebooks through Bronze→Serving, Databricks Asset Bundles deferred to `v0.5`, and Lakeflow Declarative Pipelines as the Silver→Gold transform layer at `v0.6`. What I actually wanted was the shape I'd build in production: **PySpark for Bronze** (where genuinely nested, polymorphic, malformed JSON is where Spark earns its place), **dbt for Silver and Gold** (SQL models with tests and version control — the SDLC layer notebooks never quite give you), **Genie for serving**, and **DAB from phase one** as the deploy wrapper.

The important part is that when I asked for the new shape, the AI flagged the conflict with my own pinned decision instead of quietly complying. I confirmed it as a deliberate reversal, not drift, and it got recorded as ADR-0001 and ADR-0002. DLT wasn't dropped — it moved to a later phase to be re-implemented and compared directly against dbt, because silently dropping it would have quietly killed a stated learning goal without a recorded reason.

Then came the first end-to-end run, which produced three findings in ascending order of how much it cost to learn them.

**`bundle validate` caught one thing** — the `dbt_task` also needs its own `environment_key` on serverless, not just the `spark_python_task`. That's what static validation is for. Cheap, instant.

**Running dbt locally against the real warehouse caught the next.** `databricks auth describe` reports the CLI profile's auth type as the literal string `databricks-cli`. `dbt-databricks` does not accept that literal — it wants `auth_type: oauth`, which reuses the exact same token cache (`~/.databricks/token-cache.json`), same session, no new browser flow, no PAT. No amount of YAML review finds that. You have to actually connect. (A deprecated `accepted_values` test-argument shape came out of the same run.)

**And the first real DAB job run failed outright: exit code 127, "command not found."** It is very tempting to assume a managed dbt task on Databricks means dbt is there. The auth was never the problem — that part worked. What doesn't come for free is dbt itself: serverless environments don't ship it preinstalled, and `dbt-databricks` has to be declared explicitly under the task's own `environment_key`. That's what forced splitting a dedicated `dbt_env` away from `bronze_ingest`'s `pyspark_env`. You find that by running the job, not by reading the config.

Then the best moment of the whole project. Before merging, I ran a broad automated code review — eight parallel review agents across correctness, reuse, efficiency, and repo conventions. It found five genuinely good issues and I fixed all of them: a stale architecture diagram still showing `default_env` after the job split into two environments; a hardcoded `database: novalake` in `_sources.yml` that only worked by coincidence with the catalog variable's default; a `warehouse_id` pinned to a hex ID instead of the documented `lookup:`-by-name pattern; an internal contradiction in the planning doc's own repo-structure comment (a "dev/prod targets" line that disagreed with the same doc's own "dev-only" Context section); and `checkpoint.md`'s "The decision" section not pointing readers to the "Revised decision" further down.

And a sixth suggestion, from the same review, that wasn't genuinely good: add `.cache()` before a trailing `count()` in the PySpark ingest, to avoid re-reading the source.

If you know Spark, you know this is *the* idiomatic move. It's the advice you'd give in an interview. It is correct — on a normal cluster.

The very next real run failed instantly. **Databricks serverless compute does not support `persist()`/`cache()` at all** — `NOT_SUPPORTED_WITH_SERVERLESS`. Spark Connect under the hood simply forecloses it. `bundle validate` didn't catch it. The local dbt run didn't catch it. A sound general principle, applied without knowledge of the specific runtime, produced advice that was confident, reasonable, and wrong. Reverted in seconds; the double-read costs nothing at this data size, and the comment explaining why is still in `src/ingest.py`.

That's the throughline of the whole project, and it holds for AI-suggested code and hand-written code identically: **validation catches syntax, local runs catch integration, and only real end-to-end runs catch what the platform actually does.** By `v0.9` I'd add a fourth tier — and only real runs *at real volume, against real adversarial input* catch the rest.

---

**Next up — [Part 3: Silver and Gold](LINK-PART-3).** Two pipelines that describe the same business and deliberately never unify, four distinct ways to silently lose or corrupt rows, and a refactor verification that row counts structurally cannot do.

*Part 2 of 8. Start at [Part 1](LINK-PART-1) · Full repo: [GitHub](LINK-REPO)*
