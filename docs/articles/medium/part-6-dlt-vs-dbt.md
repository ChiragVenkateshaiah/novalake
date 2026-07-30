<!--
MEDIUM METADATA — Part 6 of 8
Title:      DLT versus dbt, and getting to GB scale
Subtitle:   Three negative results and one that mattered — then rewriting both generators without losing their deliberate defects. (124 chars)
Cover:      ../poster/part-6-dlt-vs-dbt.png
SEO title:  DLT versus dbt: three negative results and one that mattered (58)
SEO desc:   EXPECT ON VIOLATION DROP ROW is a filter with telemetry, not a dead-letter queue. Plus an undocumented Free Edition table quota with no escalation path. (154)
Tags:       Databricks, dbt, Delta Live Tables, Data Engineering, Apache Spark
Source:     docs/articles/novalake-full-story.md — lines 337-431, verbatim
-->

# DLT versus dbt, and getting to GB scale

### A comparison that produced three negative results and one that mattered — then rewriting both generators at 1,000x the row count without losing a single deliberate defect

*Part 6 of 8 in **The platform is the only source of truth**, a build log of a Databricks lakehouse taken end to end on Free Edition.*
*← Previous: [The agent that leaked its own system prompt](LINK-PART-5) · Next: [Four experiments that produced numbers](LINK-PART-7) →*

---

**Where we are.** Back in [Part 2](LINK-PART-2), Lakeflow Declarative Pipelines got moved out of the main build path and deferred to a later phase, to be re-implemented and compared directly against dbt — because silently dropping it would have killed a stated learning goal without a recorded reason. This is that phase. It's also where the data stops being 5 MB, because optimization findings at that size are noise.

## The architecture, and where this part sits

The cover strip lights `SILVER` **with a dashed border** — the only part in the series drawn that way, because this is the one phase that doesn't extend the architecture. It duplicates a slice of it, on purpose, to measure the difference.

**The DLT comparison is a parallel branch, not a replacement.** A four-model Silver slice — staging → dedup → transactions → clean/DLQ split, NDJSON transactions only — gets re-implemented in Lakeflow Declarative Pipelines and written into `_dlt`-suffixed schemas that sit alongside the dbt-built ones. Same Bronze source, same business logic, two independent implementations, neither overwriting the other. That parallelism is what makes row-for-row parity checkable at all: both tables exist at once, so the comparison is a query rather than an argument.

**The GB-scale work duplicates the architecture a second way**, along a different axis. Rather than growing the existing tables, the whole spine gets a parallel `_gb` schema set — `bronze_gb`, `silver_gb`, `gold_gb` — carrying the same 101 models against ~1,000x the data. The original small-scale tables stay untouched and queryable throughout.

So by the end of this part the diagram has three coexisting copies of the same logic: the original dbt spine, a DLT re-implementation of one Silver slice, and a full GB-scale replica. Nothing was migrated. Everything was duplicated, measured, and kept — which is also why an undocumented per-schema **table count** quota turned into a real design constraint.

---

## DLT versus dbt — a comparison that produced three negative results and one that mattered

The comparison phase re-implemented a four-model Silver slice (`stg_raw_events → int_events_deduped → int_transactions → int_transactions_clean`/`_dlq`, NDJSON `transaction.*` only) in Lakeflow Declarative Pipelines, into parallel `_dlt`-suffixed schemas, never overwriting the dbt-built tables.

It was originally scoped against Gold. Planning it revealed the problem: my Gold layer is mostly plain `GROUP BY` aggregation SQL, so a DLT materialized view of it would look nearly identical to the dbt model — same SELECT, same GROUP BY, no expectations to speak of, no meaningful streaming-versus-batch question. Satisfying the original scope's literal wording would have produced almost nothing to compare. Retargeted to Silver via a new ADR that explicitly calls itself *a genuine deviation from the earlier ADR's wording, not a reinterpretation.*

**Three findings surfaced at build time that no amount of documentation reading had predicted:**

1. **Auto Loader rejects a literal file path.** First run: `Input path .../payments_events.json is not a directory`. The fix is one character of glob syntax — `payments_events[.]json` — which is functionally an exact match on the same filename but *syntactically* a glob, so it resolves as "directory with a filter."

2. **DLT rejects `ROW_NUMBER()` on a streaming table.** I wrote `events_deduped` as a `CREATE OR REFRESH STREAMING TABLE` with `ROW_NUMBER() OVER (PARTITION BY event_id ...)`, matching the dedup pattern in the DLT tooling's own documented example. It failed:

   ```
   [NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING] Window function is not
   supported in ROW_NUMBER() (as column `rn`) on streaming DataFrames/
   Datasets. Structured Streaming only supports time-window aggregation
   using the WINDOW function.
   ```

   That's a real conflict between the tool's own example and the general Structured Streaming rule — resolved live, in favor of the general rule, by falling back to `MATERIALIZED VIEW`. Which is itself the finding: where dbt and DLT have genuinely different execution models for the same intent, DLT rejected the construct outright and forced a fallback that converges on dbt's own recompute-everything model.

3. **A dataset's type is immutable once registered, even if it's empty.** Redeploying that same table as `MATERIALIZED VIEW` failed again: `[CANNOT_CHANGE_DATASET_TYPE] Cannot change the dataset type of a pipeline table from STREAMING_TABLE to MATERIALIZED_VIEW ... To change the dataset type, please drop the existing dataset first` — even though the first, failed attempt had never written a single row. Fixed with a `DROP TABLE`.

**Parity, once it built, was exact:**

| Layer | dbt | DLT | Match |
|---|---|---|---|
| bronze / raw_events | 7,105 | 7,105 | yes |
| events_deduped | 7,000 | 7,000 | yes |
| transactions | 3,192 | 3,192 | yes |
| transactions_clean | 3,042 | 3,042 | yes |
| transactions_dlq | 150 | 150 | yes |

Plus **0 mismatched rows** on an 11-column business-rule assertion across all 3,042 rows (the 11th column, `country_clean`, was added on a review pass specifically because it's the highest-drift-risk column), and 0 mismatches on a content-level Gold cross-check corrected from a tautological count-only comparison to a real `event_id` join.

### The experiment that justified the whole phase

DLT's headline data-quality primitive is `EXPECT ... ON VIOLATION DROP ROW`. It reads like a cleaner replacement for my two-model `_clean`/`_dlq` WHERE split. So I set out to check whether a dropped row's content is recoverable anywhere.

I built a scratch table, triggered a real 150-row violation, and read the event log. It reported exactly:

```json
{"passed_records": 3042, "failed_records": 150}
```

That's it. An aggregate count. **No row-level content whatsoever, anywhere queryable.** The scratch table held exactly 3,042 rows afterward; the 150 dropped rows are genuinely gone.

So DLT's headline primitive is a *filter with telemetry*, not a dead-letter queue — and dbt's boring two-model split does something it genuinely cannot replace. That's a real, empirically-confirmed architectural difference, and it's the kind of thing you only learn by triggering the violation on purpose.

Two smaller honest notes from the same phase. `EXPECT` operates on scalar per-row predicates, so it **cannot express row-uniqueness across a table** — dbt's `unique` + `not_null` test on `event_id` *is* my dedup-correctness proof, and DLT has no equivalent. I substituted a row-count parity proxy and labeled it as weaker. And the `currency_known` warn-expectation reported 94 failed records at the pre-DLQ-split grain against 90 at the `_clean`-only grain — which looks like a discrepancy for about ten minutes until you notice it's a grain-scoping question, and both sides report 94 identically.

Oh, and one non-technical finding: **Free Edition's daily compute quota is a real, hard, account-wide ceiling.** The first attempt at that experiment deployed fine and then the triggered run failed immediately with `RESOURCE_EXHAUSTED: ... you have hit your free daily limit`. Confirmed account-wide because the SQL warehouse itself started rejecting ordinary queries with the same cause. Deferred until the quota reset later the same day.

---

## GB-scale — the phase where optimization numbers stop being noise

The final phase is Spark optimization, scoped deliberately to the query and data-layout layer: query profiles, `EXPLAIN` plans, liquid clustering, `OPTIMIZE`/compaction, join strategy, skew handling, UDF elimination. Explicitly *out* of scope: executor and shuffle tuning, cluster sizing, disk cache, RDD caching — none of which serverless exposes, and writing about executor memory in an environment that structurally forbids setting it would be unverifiable content.

Prerequisite: the existing datasets are 5 MB and 7.7 MB. Optimization findings at that size are noise. So both generators got rewritten for bounded-memory chunked output.

### Rewriting generators without losing their defects

This is trickier than it sounds. Both generators encode a *deliberate defect catalog* that every downstream model and test was validated against — 10 weighted event types, v1/v2 schema drift, ~3% malformed `risk`, three sentinel timestamps, ~1.5% replay duplicates, dirty currency/country injection, plus multiline's reconciliation mismatches, dead-letter records, and cross-page merchant drift. Regeneration had to reproduce that exact catalog at ~1,000x the row count.

Two details carried the weight:

- **Duplicate injection moved to a per-chunk pass**, with duplicates stamped `ingested_at + 1s` rather than real wall-clock time — because chunking collapses the original's multi-second generation gap, and the dedup model's tie-break needs to still resolve deterministically.
- **Multiline page numbering stays global and monotonic across the whole run, independent of which file a page lands in.** That one detail is what lets the cross-page merchant-resolution SQL (`row_number() over (partition by merchant_id order by as_of_page desc)`) keep working with **zero SQL changes** — verified by reading the SQL directly, not just reasoned about.

A stated, honest caveat: chunking changes the sequence of `random.*()` calls, so re-running the unflagged script won't reproduce the currently-landed small dataset byte-for-byte. Harmless here — raw JSON is never committed to git and the small dataset is never regenerated — but stated rather than glossed.

**A ~1.01M-event pilot ran first** (649,600 NDJSON + 364,679 multiline): generation → Bronze ingest → `dbt run`/`dbt test` in **~8 minutes**, `TERMINATED SUCCESS`. What it proved, precisely rather than approximately:

- `int_events_deduped` landed at exactly **640,000** rows — 649,600 minus exactly 9,600 injected duplicates. The chunked tie-break resolves deterministically.
- `int_multiline_merchants` landed at exactly **100** across 800 pages in 40 files — empirically confirming the "zero SQL changes" cross-page claim rather than trusting it.
- Defect ratios held: sentinel timestamps 5.02% against a 5% target, malformed `risk` 2.98% against 3%.
- Bytes per event (~711 B NDJSON, ~1,890 B multiline) landed within 1% of the pre-run extrapolation.
- One live finding: `bronze_gb` didn't auto-create the way a DLT pipeline's declared schema does — plain PySpark `saveAsTable()` requires the schema to pre-exist.

Extrapolating linearly to the original 25M-event target implied **~3.3 hours** for generation + ingest + dbt alone, before running a single experiment — against a daily compute quota I'd already hit once, and job timeout ceilings I'd never tested against a run that long. So the target came down to **~5,000,000 events (~40 min extrapolated)**, set by measured pilot cost rather than by the number in the plan.

### An undocumented quota

Mid-pilot, a live Databricks warning flagged Unity Catalog approaching a per-schema table quota. Rather than trust the warning's own "80%" framing, I queried the Resource Quotas API directly:

```
novalake.silver_gb : quota_count=81, quota_limit=100
novalake.gold_gb   : quota_count=20, quota_limit=100
novalake.bronze_gb : quota_count=2,  quota_limit=100
```

Databricks' published standard quota is **10,000 tables per schema**, marked as not fixed and raisable via an account team. This 100/schema ceiling is a genuine Free Edition-specific override, silently enforced, and I could not find it stated in the Free Edition limitations page or anywhere else. There's also no escalation path: Free Edition has no account console or account-level APIs (confirmed in Databricks' own docs), sits outside the support SLA, and the one documented Free-Edition quota-increase mechanism covers serverless GPU compute and outbound internet — not UC quotas.

The useful part is *why it stays safe*: the quota tracks **model count, not row count**. `silver_gb`'s 81 plus `gold_gb`'s 20 sums exactly to the 101 applicable dbt models. Full-scale runs refresh those tables in place. But `silver_gb`'s 19 tables of headroom became a standing design constraint on every subsequent experiment — no new physical table unless explicitly justified, dropped immediately after, and preferring `gold_gb` (80 free) when unavoidable.

---

**Next up — [Part 7: Four experiments that produced numbers](LINK-PART-7).** A generator bug that duplicated 122,592 rows, an 86% improvement caused by nothing at all, and a result cache that matched on logical meaning rather than query text.

*Part 6 of 8. Start at [Part 1](LINK-PART-1) · Full repo: [GitHub](LINK-REPO)*
