<!--
MEDIUM METADATA — Part 7 of 8
Title:      Four experiments that produced numbers
Subtitle:   122,592 duplicated rows, an 86% improvement caused by nothing, and a result cache that matched on meaning, not text. (120 chars)
Cover:      ../poster/part-7-four-experiments.png
SEO title:  Four Spark experiments that produced real numbers (48)
SEO desc:   Liquid clustering, compaction and join strategy measured on 2.1M rows — plus the cache artifact that nearly got reported as an 86% win. (137)
Tags:       Apache Spark, Databricks, Performance, Data Engineering, Delta Lake
Source:     docs/articles/novalake-full-story.md — lines 433-505, verbatim
-->

# Four experiments that produced numbers

### A generator bug that duplicated 122,592 rows, an 86% improvement caused by nothing at all, and a result cache that matched on logical meaning rather than query text

*Part 7 of 8 in **The platform is the only source of truth**, a build log of a Databricks lakehouse taken end to end on Free Edition.*
*← Previous: [DLT versus dbt, and getting to GB scale](LINK-PART-6) · Next: [The one that didn't resolve](LINK-PART-8) →*

---

**Where we are.** [Part 6](LINK-PART-6) rewrote both generators for GB scale without losing their deliberate defect catalog, ran a ~1.01M-event pilot, and set the real target at ~5,000,000 events based on measured pilot cost rather than the number in the plan. Then the full run happened, and `dbt test` came back with three errors that weren't in the baseline.

---

## The generator bug that duplicated 122,592 rows

Stage 2 of the full run — multiline — completed generation and Bronze ingest fine. `dbt run` succeeded on all 101 models. Then `dbt test` came back `PASS=295 WARN=7 ERROR=3`. The 7 warnings matched the known baseline exactly. The 3 errors were new, and two of them shared the *identical* duplicate count: **122,592**, on `unique_fct_transactions_transaction_key` and `unique_int_multiline_transactions_fx_applied_event_id`. The third was a 400-row duplicate on the reconciliation table's `page`.

A `GROUP BY page HAVING count(*) > 1` showed 4,400 total pages against 4,000 distinct, min 1 and max 4,000, with duplicates starting **exactly at page 401** — a clean 400-page range. That's not a random corruption pattern; that's an overlap.

A direct `databricks fs ls` on the landing directory found the answer: **40 files, not 20.** Files `00000`–`00019` were this run's, ~180 MB each, matching `--pages-per-file 200`. Files `00020`–`00039` were untouched leftovers from the *pilot* run, ~18 MB each, matching the pilot's `--pages-per-file 20`.

The multiline generator never cleared its output directory. This run produced fewer files (20) than the pilot had (40) at the same path, so the pilot's higher-indexed files survived — and Spark's directory scan happily read all 40. Both runs restart page numbering at 1, so the overlap silently duplicated pages 401–800.

Fixed permanently — glob and remove all prior part-files at the start of every run, not a one-off cleanup. Remediation: delete the 20 stale files, re-run the multiline Bronze ingest alone, confirm `bronze_gb.raw_events_multiline` holds exactly 4,000 pages.

Then a genuinely useful detour. I tried to rebuild only the affected subgraph cheaply, via a scoped `dbt run --select source:...+` passed through the job's task-parameter override — and the CLI rejected it flatly: *"the job to run defines job parameters; specifying task parameters is not allowed."* Job-level `--params` (already used for event counts) and task-level command overrides cannot coexist on the same job resource. That's a hard rule, not a config problem.

The redesign I drafted (parameterize the dbt task's trailing args as a job parameter) went out for a second-model review that found three load-bearing problems with it, including that `commands:` is free-form text with **no validator** — unlike the identifier-validated `catalog:` field, a bad substitution there fails at *run* time rather than deploy time, possibly silently. And the review's most useful finding was that for the immediate need, **running dbt locally sidesteps the entire problem**: same warehouse, same cost, full `--select` freedom, zero YAML change, zero redeploy, none of the three risks.

Which is what I did. 68 models rebuilt cleanly, `PASS=218 WARN=4 ERROR=0`, all three failing tests green. And then verified independently rather than trusting dbt's own test result: `fct_transactions` row count exactly equals its distinct `transaction_key` count (**2,138,809 = 2,138,809**), reconciliation table exactly 4,000 rows across 4,000 distinct pages.

---

## Six experiments, five results, one open question

The final table is `gold_gb.fct_transactions` at **2,138,809 rows**.

*This part covers experiments 8.1 through 8.4 — the four that produced measured, causally-explained numbers. [Part 8](LINK-PART-8) covers the remaining two, plus the scorecard.*

**8.1 — Baseline.** `SELECT * FROM gold_gb.fct_transactions WHERE merchant_id = 'mer_1050'` returns 8,525 rows, about 0.4% of the table. It read **2 files, 123,778,745 bytes (~118 MB), 0 bytes spilled, in 6,831 ms.** That's essentially the entire table's byte volume to retrieve 0.4% of its rows — the textbook case for data skipping, sitting right there in the query profile.

*(Methodology note that cost real time: `system.query.history`, where read_bytes and read_files live, has no documented freshness SLA. Sometimes instant; once it took 7 polls at 30-second intervals. The working pattern is two-tier — the fast Query History API for immediate summary signal, a background polling loop against the system table for full metrics.)*

**8.2 — Liquid clustering, and a null result I nearly mis-reported as a win.** `ALTER TABLE ... CLUSTER BY (merchant_id)` succeeded, which itself confirmed liquid clustering is available on Free Edition. Then `OPTIMIZE` returned **`numFilesAdded: 0, numFilesRemoved: 0`** — and its own metrics explained why: `nodeMinNumFilesToCompact: 4` against `totalConsideredFiles: 2`. A 2-file table sits below the threshold Delta's clustering optimizer requires before physically rewriting anything.

Re-running the identical query: same 8,525 rows, same 2 files, 124,759,488 bytes (0.8% more — noise), and **944 ms, down from 6,831 ms. An 86% improvement.**

That 86% is not clustering. Bytes and files are unchanged *to the byte*. It's a warehouse/cache warm-up artifact from the query I'd run moments earlier. If I'd reported duration alone — which is the number that looks best in a slide — I'd have published an 86% improvement caused by nothing. **A config change and a physical effect are different things.**

**8.2b — So test it properly.** Built a disposable scratch copy (`CREATE TABLE ... AS SELECT *`, exact 1:1, no duplication — duplicating rows in the real table would have corrupted the `transaction_key` uniqueness I'd just fixed). First fragmentation attempt: set `delta.targetFileSize='16mb'` and run `OPTIMIZE`. It did **nothing** (`numFilesAdded: 0, totalFilesSkipped: 2`) — an unplanned finding worth its own line: **bin-packing `OPTIMIZE` only merges small files toward a target, it never splits large ones.** Forced it instead with `INSERT OVERWRITE ... SELECT /*+ REPARTITION(8) */ *`, row count confirmed unchanged.

Fragmented-but-unclustered baseline: 8 files, ~118 MB, 1,751 ms — same bytes as before, confirming file count alone buys nothing.

Then `CLUSTER BY (merchant_id)` + `OPTIMIZE`: **`numFilesAdded: 9, numFilesRemoved: 8`, `approxClusteringQuality: 0.784`** — a genuine physical rewrite.

Result: **1 file read (down from 8), 13,529,071 bytes (~12.9 MB, down 89%), 1,551 ms.**

Files −87.5%, bytes −89%, duration −11%. That last number is the interesting one: at this scale, fixed per-query overhead dominates wall-clock so thoroughly that an 89% I/O reduction shows up as an 11% duration improvement. Which is exactly why 8.2's 86% duration drop with *zero* I/O change should have been suspicious immediately.

**8.3 — Compaction, with two methodology confounds caught first.** Surveying `DESCRIBE DETAIL` across `bronze_gb` found `raw_events_multiline` genuinely fragmented: 20 files, ~11.1 MB average, well past the 4-file threshold.

Before trusting anything, I checked `system.storage.predictive_optimization_operations_history` — because `SHOW TBLPROPERTIES` showed nothing about Predictive Optimization at all. It had already compacted an earlier version of this exact table earlier the same day, 23 files → 4. **Predictive Optimization is genuinely active on this workspace and completely invisible to `SHOW TBLPROPERTIES`.** If you're benchmarking file layout on Databricks and not checking that table, your "before" can change under you.

Then two confounds:
1. My first candidate query (`count(*)`, `max(...)`) came back as **`LocalTableScan`** in `EXPLAIN` — zero bytes read, even with `SET use_cached_result = false`. Delta answered it entirely from file-level metadata statistics. Useless for measuring a file-layout change.
2. Switched to an aggregate over nested array content (`sum(size(data.events))`), confirmed via `EXPLAIN` to force a genuine `PhotonScan`.

Baseline: 20 files, 219,241,796 bytes (~209 MB), 7,777 ms. `OPTIMIZE` returned `numFilesAdded: 4, numFilesRemoved: 20`. After: **4 files, 202,334,925 bytes (−7.7%), 3,120 ms (−60%).**

Unlike 8.2, both bytes *and* files genuinely moved, so the duration improvement has a real causal mechanism — fewer files means less per-file open and scheduling overhead on a full scan. And the contrast with 8.2b is the actual lesson: **compaction helps full scans by cutting per-file overhead (files drop a lot, bytes barely move); clustering helps filtered queries by skipping files entirely (both drop a lot).** Different problems, visible in which metric moves.

**8.4 — Join strategy, and the result cache that quietly invalidated my first measurement.** Part A, small-dimension: `fct_transactions` (2.1M) × `dim_merchants` (100) on `merchant_id`. `EXPLAIN` confirmed the default is `PhotonBroadcastHashJoin`. Forced `/*+ SHUFFLE_HASH */` → `PhotonShuffledHashJoin`, still fully Photon. Forced `/*+ MERGE */` → a real `SortMergeJoin`, and **Photon explicitly declines to run it**, falling back to classic Spark.

The first measurement came back with `read_bytes=0` and `read_files=0` for both hinted variants — despite real `PhotonScan` nodes in their own `EXPLAIN` plans. Checking `from_result_cache` and `cache_origin_statement_id` in `system.query.history` directly gave the answer: both had been served from the **default query's cached result**. Databricks' result cache matches on **logical result equivalence, not literal query text** — and a join hint doesn't change declarative semantics, so all three queries were "the same query" as far as the cache was concerned.

A per-call `SET use_cached_result = false` did nothing, because each CLI/API call is its own stateless session. The fix was creating an explicit SQL session via `POST /api/2.0/sql/sessions` and reusing its `session_id` across the `SET` and every subsequent query.

Cache-verified, same-warm-session results (all three correctness-checked at 2,111,585 rows, and identical at 3 files / 2,467,304 bytes, as expected for a join-strategy test):

| Strategy | Duration | vs default |
|---|---|---|
| default (`PhotonBroadcastHashJoin`) | 888 ms | — |
| `SHUFFLE_HASH` | 1,083 ms | +22% |
| `MERGE` (`SortMergeJoin`, non-Photon) | 2,095 ms | +136% |

Part B, large-large: `int_events_deduped` (3,200,000) × `int_transactions` (1,439,742) on `event_id`, deliberately kept within the NDJSON source per this project's own cross-source guardrails. Spark's own default here was `PhotonShuffledHashJoin`, not `SortMergeJoin` — 1.44M rows is still small enough to hash-build. First measurement made `MERGE` look like the winner (2,450 ms vs 6,591 ms) until I noticed the default had run *first in a brand-new session* and was paying the cold-start tax. Re-measured warm: **default 1,311 ms, `MERGE` 2,038 ms (+55%)** — same direction, smaller relative penalty at larger scale.

Two things worth keeping. **Spark's default join selection was correct in both scenarios; forcing a non-default strategy never won.** And `shuffle_read_bytes` stayed **exactly 0** across both parts despite Part B's genuine 80 MB, 16-way-partitioned shuffle — read as a real platform signal (this serverless warehouse runs on few enough nodes that shuffle stays local and never crosses the network), not a broken metric.

Also: a session's first real query pays a cold-start tax, confirmed three separate times across this phase. **Never trust a "before" measurement that ran first in a session.**

---

**Next up — [Part 8: The one that didn't resolve](LINK-PART-8).** Skew handling reported as inconclusive rather than dressed up, a Python UDF that made Photon decline every downstream stage, the scorecard for all six experiments, and what I'd actually take from the whole build.

*Part 7 of 8. Start at [Part 1](LINK-PART-1) · Full repo: [GitHub](LINK-REPO)*
