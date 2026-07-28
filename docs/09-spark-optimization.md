# Module 9 · Spark Optimization (Serverless-Constrained)

`Status:` Draft — GB-scale full run complete and validated (2026-07-28);
`§8` optimization experiments in progress (8.1, 8.2, 8.2b, 8.3, 8.4 done) ·
`Owner:` Chirag · `Last updated:` 2026-07-28 · `Est. time:` multi-session

**Scope, per [ADR-0008](adr/0008-novalake-terminus-and-cerberus-succession.md):**
"Spark optimization within serverless constraints, capped deliberately at the
query/data-layout layer — query profiles, `EXPLAIN` plans, liquid clustering,
`OPTIMIZE`/file compaction, join strategy, skew handling, UDF elimination."
Explicitly **out of scope** (deferred to a future project, Cerberus, on
classic Spark compute): executor/shuffle tuning, cluster sizing, disk-cache,
RDD-level caching — none of it is reachable on Free Edition serverless
anyway (no Spark UI, no cluster sizing, most `spark.conf` locked).
**`v0.9` is NovaLake's terminus — no `v0.10`.** GB-scale data regeneration
(the prerequisite this module needs) is its own decision record,
[ADR-0011](adr/0011-gb-scale-data-regeneration.md).

## 1. Learning Objectives
- [x] Can capture a real Query Profile (bytes scanned, files read, wall-clock)
      for a Databricks SQL warehouse query using two different live sources —
      the fast Query History API (near-instant, but summary-level only:
      duration/rows) and `system.query.history` (full metrics, but no
      documented freshness SLA — confirmed directly, not assumed) — and knows
      which one to reach for depending on what's needed
- [x] Can explain why `ALTER TABLE ... CLUSTER BY` alone never changes a
      table's physical layout — and what condition (a minimum-files-to-compact
      threshold, visible in `OPTIMIZE`'s own returned metrics) determines
      whether a subsequent `OPTIMIZE` actually rewrites anything
- [x] Can distinguish a real I/O-level optimization effect (bytes/files
      scanned) from a warehouse-warm/cache artifact (wall-clock alone) when
      reading a before/after comparison — and knows why trusting duration by
      itself would have produced a false "clustering worked" conclusion here
- [x] Can force a table's physical file layout to change (for a controlled
      experiment) without altering its data or breaking key uniqueness — and
      knows why a disposable scratch copy, not the real table, is the safe
      way to do that
- [x] Can explain why bin-packing `OPTIMIZE` alone won't split large files
      into smaller ones (it only merges small files toward a target size),
      and what forces a real rewrite instead (an explicit repartitioned
      `INSERT OVERWRITE`)
- [x] Has directly observed liquid clustering's real data-skipping effect
      (files read 8→1, bytes read ~118 MB→~12.9 MB) once a table is past the
      minimum-files-to-compact threshold — not just inferred it from
      `8.2`'s null result
- [x] Can find genuine (not artificial) file fragmentation by surveying
      `DESCRIBE DETAIL` across candidate tables, and can detect whether
      Predictive Optimization has already acted on a table using
      `system.storage.predictive_optimization_operations_history` — a real
      operations log, unlike `SHOW TBLPROPERTIES`, which shows nothing about
      Predictive Optimization activity at all
- [x] Can recognize when a query will be answered from Delta's file-level
      metadata statistics alone (`LocalTableScan` in the plan, zero bytes
      actually read) rather than a real physical scan — and knows this makes
      such a query useless for measuring a file-layout change, regardless of
      whether the query result cache is also a factor
- [x] Can explain *why* file compaction improves a full, unfiltered scan
      (fewer files → less per-file open/schedule overhead) as a mechanism
      distinct from liquid clustering's data-skipping benefit for filtered
      queries — and can tell the two apart from the shape of a before/after
      result (compaction: files drop a lot, bytes barely move, duration drops
      a lot; clustering: files *and* bytes both drop a lot for a filtered
      query)
- [x] Can force a join strategy via a SQL hint (`SHUFFLE_HASH`, `MERGE`) and
      confirm via `EXPLAIN` it was actually honored — and knows that forcing
      `MERGE` (`SortMergeJoin`) causes a **fallback out of Photon
      acceleration entirely** on this platform, a real cost beyond just "a
      different shuffle strategy"
- [x] Can recognize a subtle result-cache behavior: Databricks' SQL result
      cache matches on **logical result equivalence**, not literal query
      text — a join hint doesn't change the declarative semantics, so
      differently-hinted queries can silently share one cache entry even
      with guaranteed-unique query text. Knows the actual fix: a bare `SET
      use_cached_result = false` in a stateless tool call does nothing,
      because each such call may be a fresh session; the real fix is an
      explicit session (`POST /api/2.0/sql/sessions`, reusing its
      `session_id` across calls)
- [x] Can recognize a session's first-query cold-start tax (confirmed a
      third time this module) and knows to always re-measure a "default"/
      baseline warm, in the same session as the variants being compared —
      not trust whichever number happened to run first
- [x] Can explain why `shuffle_read_bytes` staying at exactly 0 for a real,
      large (80 MB, 4.6M-row) shuffle isn't a measurement bug — it means no
      data crossed the network, consistent with this workspace's serverless
      warehouse running on few enough nodes that "shuffle" stays local
- [ ] `8.5`–`8.6` objectives — not yet reached

## 2. Prerequisites
- `v0.9`'s GB-scale regeneration (ADR-0011) complete and validated: `bronze_gb`/
  `silver_gb`/`gold_gb` hold ~5,000,000-event data from both raw sources,
  101 dbt models rebuilt, `dbt test` clean (`PASS=218 WARN=4 ERROR=0` on the
  remediated multiline/Gold slice — see `docs/checkpoint.md`'s 2026-07-28
  entries for the full story, including a real generator bug found and fixed
  along the way)
- `gold_gb.fct_transactions` exists: 2,138,809 rows, unclustered at the start
  of `§8`

## 3. Where This Fits (Architecture Context)
- Input: `gold_gb`/`silver_gb`/`bronze_gb` — already built by dbt from the
  full-scale raw sources (`v0.9`'s earlier steps, ADR-0011 §5–§6)
- This module: applies and measures Spark/Delta optimization techniques
  directly against the already-built Delta tables, on the SQL warehouse —
  deliberately independent of whichever tool (dbt here) built those tables.
  `§8`'s experiments would run identically regardless of build tool; this
  module doesn't touch dbt models except to permanently fold in a config
  change if an experiment shows a genuine win (per `§6`'s `is_gb_scale`
  mechanism, e.g. adding `liquid_clustered_by` to a model's `config()`)
- Output: a documented before/after result for each of ADR-0008's six named
  techniques, honest about nulls and negative results, not just wins

## 4. Concepts & Background
- **Query Profile, two sources, two different freshness guarantees.** The SQL
  UI's Query Profile tab (and the equivalent Query History REST API,
  `/api/2.0/sql/history/queries`) surfaces `duration`/`rows_produced` almost
  immediately after a query finishes. The fuller metrics — `read_bytes`,
  `read_files`, `spilled_local_bytes` — only live in the `system.query.history`
  table, which Databricks has **no documented freshness SLA** for (a
  Databricks engineer confirmed this directly on a community thread: "We
  don't offer data freshness SLOs for system tables at this point"). In
  practice this session, the same kind of query landed instantly on one
  check and took 7 polls at 30-second intervals (~3.5 minutes) on another —
  plan for this by polling, not assuming instant availability, and don't
  block other work waiting on it.
- **Liquid clustering is a two-step, not a one-step, operation.**
  `ALTER TABLE ... CLUSTER BY (col)` only sets clustering *metadata* — free,
  instant, and by itself changes nothing about how the table is stored on
  disk. The actual physical reorganization (grouping rows by the clustering
  key across files) only happens when `OPTIMIZE` runs and decides a rewrite is
  worth doing.
- **Real pitfall, found live, not assumed: `OPTIMIZE` has an internal
  minimum-files-to-compact threshold.** Its own returned metrics include
  `nodeMinNumFilesToCompact` — if the table's current file count doesn't meet
  that threshold, `OPTIMIZE` runs successfully (no error) but does nothing
  (`numFilesAdded: 0, numFilesRemoved: 0`). This means "I ran `OPTIMIZE`" is
  **not** proof "my table is now clustered on disk" — the only real evidence
  is `OPTIMIZE`'s own file-added/file-removed counts, or a `DESCRIBE DETAIL`
  file-count/size diff before and after.
- **A wall-clock improvement alone is not proof an optimization worked.**
  Two runs of the same query against byte-for-byte identical physical files
  can still show a large duration difference from warehouse/cache warm-up —
  this module's `8.2` result is the concrete example (see below).
- **Bin-packing `OPTIMIZE` merges small files; it does not split large
  ones.** Lowering a table's `delta.targetFileSize` property has no effect
  on files that are already at or above that size — `OPTIMIZE` only
  considers rewriting when there's a *small*-file problem to fix. Forcing an
  already-large file to split requires an explicit rewrite (e.g. an
  `INSERT OVERWRITE ... SELECT /*+ REPARTITION(n) */ ...`), not a property
  change plus a plain `OPTIMIZE` call.
- **Predictive Optimization is genuinely active on this workspace — and
  `SHOW TBLPROPERTIES` gives zero indication of it.** The only real evidence
  is `system.storage.predictive_optimization_operations_history`, an actual
  operations log (confirmed live: it had already run a `COMPACTION` on an
  earlier version of `bronze_gb.raw_events_multiline` earlier the same day,
  23→4 files). Check this table before trusting any `OPTIMIZE` before/after
  comparison — if Predictive Optimization compacts a table between your
  "before" measurement and your own `OPTIMIZE` call, your own `OPTIMIZE` will
  look like a no-op when PO already did the work.
- **Two separate confounds can make a query silently stop measuring what you
  think it measures — neither is about clustering/compaction at all.**
  (1) Delta can answer simple aggregates (`COUNT(*)`, `MAX(scalar_col)`)
  straight from file-level metadata statistics, with **zero bytes read** —
  visible in the plan as `LocalTableScan`. No file-layout change can ever
  show up in such a query's metrics, because no file is ever opened. (2) The
  SQL warehouse's query result cache can return an identical result for a
  repeated query without re-scanning anything — set `use_cached_result =
  false` for the session before any before/after comparison, and pick a
  query shape (e.g. an aggregate over nested array content, not a bare
  `COUNT(*)`) that forces a genuine `PhotonScan`, confirmed via `EXPLAIN`
  before trusting the result.
- **The result cache's real matching key is logical result equivalence, not
  literal SQL text — and a bare `SET` in a stateless call doesn't disable
  it.** `8.4` found this the hard way: a join-strategy hint doesn't change a
  query's declarative semantics (same tables, same predicate, same output),
  so Databricks' cache treated three hint-differing queries as "the same
  query" and served one cached result to all three — confirmed directly via
  `from_result_cache`/`cache_origin_statement_id` in `system.query.history`.
  Neither disabling the cache via a separate `SET use_cached_result = false`
  call nor giving each query a unique output alias fixed it, because each
  MCP/CLI tool call is its own stateless session — a session-scoped `SET`
  from one call has no effect on the next. The actual fix: create an
  explicit session first (`POST /api/2.0/sql/sessions` → a real
  `session_id`), then pass that same `session_id` on every subsequent
  `POST /api/2.0/sql/statements` call (`SET`, then each query) — only then
  does the `SET` actually apply to what follows.
- **A session's first real query pays a cold-start tax, confirmed three
  times now (`8.2`, `8.4`'s two sub-tests).** Never trust a "before" or
  "default" measurement that happened to be the very first query issued in
  a session — re-measure it warm, in the same session as whatever it's being
  compared against, before drawing a conclusion from a duration gap.
- **`shuffle_read_bytes = 0` on a real shuffle isn't a bug — it's a platform
  signal.** This column measures bytes sent *over the network*. Seeing it at
  exactly 0 for a real, large (80 MB, 16-way-partitioned) shuffle — twice,
  at two different scales — is strong evidence this workspace's serverless
  warehouse runs on few enough nodes that shuffle exchanges stay local,
  never crossing the network. Consistent with ADR-0008's broader
  limited-infra-visibility theme for this platform.

## 5. Data Contract / Schema in Scope
- `novalake.gold_gb.fct_transactions` — 2,138,809 rows, 21 columns, unclustered
  at experiment start (`clusteringColumns: []`, `clusterByAuto: false`,
  2 files, 123,263,770 bytes total)
- Representative query used throughout `8.1`/`8.2`:
  `SELECT * FROM gold_gb.fct_transactions WHERE merchant_id = 'mer_1050'`
  (`mer_1050` is a non-skewed merchant — 8,525 matching rows, ~0.4% of the
  table, consistent with ADR-0011's skew design where only `mer_1000`/
  `mer_1001` are deliberately hot)
- `novalake.bronze_gb.raw_events_multiline` — 4,000 rows (one per multiline
  "page"), 7 columns (deeply nested), 20 files at experiment start
  (~11.1 MB avg, ~212 MB total), unclustered, from ingesting 20 separate
  landing part-files. Representative query for `8.3`:
  `SELECT count(*), sum(size(data.events)) FROM bronze_gb.raw_events_multiline`
  (a full, unfiltered scan over nested array content — chosen specifically
  because it can't be answered from Delta metadata alone, see §4)
- `8.4`'s two join candidates: `gold_gb.fct_transactions` (2.1M-row fact) ×
  `gold_gb.dim_merchants` (100-row dimension) on `merchant_id` — small-dim
  case, Spark auto-broadcasts by default; and `silver_gb.int_events_deduped`
  (3,200,000 rows, all deduped events) × `silver_gb.int_transactions`
  (1,439,742 rows, the transaction-type subset) on `event_id` — a genuine
  large-large, foreign-key-like join (the second table is literally derived
  from the first by filter), staying within the ndjson source per this
  project's guardrail against joining ndjson/multiline identifiers across
  sources

## 6. Step-by-Step Implementation

- **Step 8.1 — Baseline capture**
  - *Objective:* establish a real, unmodified reference measurement before
    any optimization technique is applied — everything later in `§8` diffs
    against this.
  - *Concept:* `EXPLAIN`/`EXPLAIN FORMATTED` give the plan shape; real
    execution metrics (not estimates) come from actually running the query
    and capturing its Query Profile.
  - *Task:* `EXPLAIN` + `EXPLAIN FORMATTED` on the representative query, then
    execute it and pull `read_rows`/`read_bytes`/`read_files`/
    `spilled_local_bytes`/`total_duration_ms` from `system.query.history`.
  - *Expected output / observed:* fully Photon-native plan
    ("The query is fully supported by Photon"), `merchant_id` pushed down as
    both a data filter and a dictionary filter. Executed: **8,525 rows,
    2 files read, 123,778,745 bytes read (~118 MB), 0 bytes spilled,
    6,831 ms wall-clock.**
  - *Validation check:* `DESCRIBE DETAIL` confirmed `clusteringColumns: []`,
    `clusterByAuto: false`, and `lastModified` (11:49:03) exactly matching
    when the dbt rebuild finished — no background process (Predictive
    Optimization or otherwise) touched the table between the rebuild and this
    baseline, so the measurement is clean.
  - **The headline number**: 123,778,745 bytes read is almost exactly the
    table's entire 123,263,770-byte size — this query had to scan
    essentially 100% of the table's bytes to return 0.4% of its rows. That
    gap is the entire reason `8.2` exists.

- **Step 8.2 — Liquid clustering**
  - *Objective:* test whether clustering `fct_transactions` by `merchant_id`
    reduces the bytes/files scanned for the same representative query.
  - *Concept:* liquid clustering's data-skipping benefit depends on physical
    file reorganization, not just the clustering property being set — see
    §4's pitfall.
  - *Task (gated, ADR-0009):* `ALTER TABLE novalake.gold_gb.fct_transactions
    CLUSTER BY (merchant_id)`, then `OPTIMIZE novalake.gold_gb.fct_transactions`
    — the second statement is what actually reclusters existing data. Then
    re-run the identical query from `8.1` and re-capture the same metrics.
  - *Expected output / observed:*
    - `ALTER TABLE` succeeded immediately — **confirms liquid clustering is
      genuinely available on this Free Edition workspace**, the live check
      the `v0.9` plan explicitly flagged as unverified before committing to
      this technique.
    - `OPTIMIZE` returned `numFilesAdded: 0, numFilesRemoved: 0` — **no
      physical rewrite happened.** Its own metrics show
      `nodeMinNumFilesToCompact: 4` against `totalConsideredFiles: 2` — the
      table's 2 files sit below the threshold Delta's clustering optimizer
      requires before it considers a rewrite worthwhile.
    - `DESCRIBE DETAIL` afterward: `clusteringColumns: ["merchant_id"]` now
      set, table feature `"clustering"` added — but `numFiles: 2` and
      `sizeInBytes: 123,263,770` **unchanged to the byte** from before
      `OPTIMIZE` ran.
    - Re-running the identical query: **8,525 rows (same), 2 files read
      (same), 124,759,488 bytes read (0.8% more, not less — within
      measurement noise, not a real change), 944 ms wall-clock — an 86%
      reduction from 6,831 ms.**
  - *Validation check:* `OPTIMIZE`'s own returned metrics (not just "it ran
    without error") plus a `DESCRIBE DETAIL` byte-for-byte diff are the real
    evidence here — a config change alone is not sufficient proof of a
    physical effect.
  - **Conclusion — a clean, honest null result, not a bug:** clustering had
    zero effect on I/O, exactly as expected once the file count is known to
    be below the compaction threshold. Bytes/files scanned are unchanged
    (within noise); there was never a physical reorganization for clustering
    to benefit from. The 86% wall-clock improvement is **not attributable to
    clustering** — since the physical bytes/files are identical, the far more
    likely explanation is a warm SQL-warehouse/cache effect carried over from
    running the same query moments earlier, not a real optimization. Recorded
    as a genuine negative result for this table at this file count, not
    glossed over as a win because the duration number looked good.
  - **Bridge to `8.2b` below:** `8.2`'s null result is fully explained by
    `OPTIMIZE`'s own metrics — but a config-level explanation isn't the same
    as watching the real mechanism work. Verified directly, not left as an
    inference.

- **Step 8.2b — Empirical verification: does clustering actually work once
  past the file threshold?**
  - *Objective:* confirm directly that clustering's data-skipping benefit is
    real once a table has enough files, rather than stopping at "here's why
    it didn't fire on `fct_transactions`."
  - *Concept:* `8.2`'s null result was about file *count*, not row *count* —
    so the test needs to change file count without changing the data itself,
    keeping the comparison as close as possible to `8.1`/`8.2`'s real
    scenario (same rows, same distribution, only the physical layout
    differs).
  - *Task (gated, ADR-0009):* built a disposable scratch copy,
    `novalake.gold_gb._scratch_fct_transactions_clustering_test`, rather than
    touching the real `fct_transactions` directly — duplicating rows in
    place (e.g. `INSERT INTO ... SELECT * FROM ...`) would have created
    duplicate `transaction_key` values, corrupting the exact uniqueness
    invariant this project just fixed in the multiline remediation
    (`docs/checkpoint.md`, 2026-07-28). Matches the scratch-table discipline
    ADR-0011's `§8` addendum and `v0.7`'s `_scratch_dlq_test` precedent both
    established: gated creation, dropped immediately after use, no lasting
    footprint.
    - **First attempt at forcing fragmentation didn't work — a real,
      unplanned-for finding, not glossed over:** set
      `delta.targetFileSize = '16mb'` on the scratch copy, then ran a plain
      `OPTIMIZE` (no clustering yet). Result: `numFilesAdded: 0,
      numFilesRemoved: 0`, `totalFilesSkipped: 2` — nothing happened. Plain
      bin-packing `OPTIMIZE` only *merges* small files toward a target size;
      it does not *split* already-large files just because the target
      shrank. Lowering `targetFileSize` alone was not sufficient.
    - **Fix:** forced an explicit rewrite instead —
      `INSERT OVERWRITE novalake.gold_gb._scratch_fct_transactions_clustering_test
      SELECT /*+ REPARTITION(8) */ * FROM
      novalake.gold_gb._scratch_fct_transactions_clustering_test` — identical
      2,138,809 rows (confirmed via `num_affected_rows`/`num_inserted_rows`),
      identical content, physically split across 8 files by the repartition
      hint.
  - *Expected output / observed:*
    - Fragmented, unclustered baseline (8 files): **8,525 rows, 8 files read,
      124,012,429 bytes read (~118 MB), 1,751 ms** — essentially the same
      bytes as the original 2-file baseline, confirming an unclustered table
      gets no benefit from file count alone; every file still had to be
      scanned since `merchant_id` values are scattered evenly across all of
      them.
    - `ALTER TABLE ... CLUSTER BY (merchant_id)` + `OPTIMIZE`: this time
      returned **`numFilesAdded: 9, numFilesRemoved: 8`** and a real
      `approxClusteringQuality: 0.784` — a genuine physical rewrite, unlike
      `8.2`'s no-op.
    - Clustered result: **8,525 rows, 1 file read, 13,529,071 bytes read
      (~12.9 MB), 1,551 ms.**
  - *Validation check:* `DESCRIBE DETAIL` confirmed the physical file-count/
    size change at every stage (2 → 8 → 9 files); row count verified
    unchanged throughout — this was purely a file-layout experiment, never a
    data change.
  - **Conclusion — clustering's mechanism confirmed directly, not just
    inferred:** once past the file-count threshold, clustering + `OPTIMIZE`
    cut files read from 8 → 1 (**−87.5%**) and bytes read from ~118 MB → ~12.9
    MB (**−89%**). Duration only improved 11% (1,751 ms → 1,551 ms) despite
    the 89% I/O reduction — reinforcing `8.2`'s own finding that fixed
    per-query overhead (planning, Photon startup, network round-trip)
    dominates wall-clock at this data scale, so bytes/files scanned remains
    the metric that actually reflects an optimization's effect, not duration
    alone.
  - Scratch table dropped immediately after (`DROP TABLE`) — no lasting
    footprint, no quota consumed beyond the comparison itself.
  - **Bridge to `8.3` (`OPTIMIZE`/file compaction, next):** `fct_transactions`
    itself has no room to show a clustering benefit at 2 files — that
    conclusion stands, confirmed rather than just inferred. `8.3`'s own
    candidate-table search across `bronze_gb`/`silver_gb`/`gold_gb` should
    specifically look for a table with more files/fragmentation (the small
    per-part-file Bronze tables are a likely candidate) — and, per this
    step's finding, remember that plain compaction `OPTIMIZE` doesn't split
    large files, only merges small ones, when picking a technique.

- **Step 8.3 — `OPTIMIZE`/file compaction**
  - *Objective:* find a table with genuine (not artificial) file
    fragmentation and measure whether plain bin-packing `OPTIMIZE` (no
    clustering) improves a full-scan query's cost.
  - *Concept:* compaction's mechanism is different from clustering's — it
    reduces *per-file overhead* for scans that touch most/all of a table
    (fewer files → fewer open/close and task-scheduling costs), rather than
    *skipping* files for a filtered query. A good candidate table needs many
    small files, not a filter-worthy key.
  - *Task:* surveyed `DESCRIBE DETAIL` across `bronze_gb` (the smallest,
    fastest schema to check, and the plan's own suggested first look, since
    Bronze ingest from many landing part-files is a likely small-files
    source). `bronze_gb.raw_events` was unremarkable (4 files); `bronze_gb
    .raw_events_multiline` had **20 files, ~11.1 MB average** — a genuine
    small-files table, well past the 4-file compaction threshold `8.2b`
    found. Checked `system.storage.predictive_optimization_operations_history`
    before trusting anything: Predictive Optimization had already run a real
    `COMPACTION` on an earlier version of this same table earlier the same
    day (23→4 files, `2026-07-28T10:42:45Z`) — confirming PO is genuinely
    active on this workspace (something `SHOW TBLPROPERTIES` gave zero
    indication of), and that the current 20-file state postdated that event
    with nothing since, so the "before" measurement was still clean. Acted
    promptly given PO could compact it again at any time.
  - **Two real methodology confounds found and fixed before trusting any
    number, neither related to compaction itself:**
    1. The first candidate query, `SELECT count(*), max(pagination.page)
       FROM ...`, came back as `LocalTableScan` in `EXPLAIN` — **zero bytes
       read** — even after disabling the query result cache
       (`SET use_cached_result = false`). Delta answered it entirely from
       file-level metadata statistics. No file-layout change could ever show
       up in this query's metrics, cache or no cache.
    2. Switched to `SELECT count(*), sum(size(data.events))
       FROM bronze_gb.raw_events_multiline` — an aggregate over nested array
       content, confirmed via `EXPLAIN` to produce a genuine `PhotonScan`
       with no `RequiredDataFilters` (a real full scan). This is the query
       used for both before/after measurements below.
  - *Task (gated, ADR-0009):* `OPTIMIZE novalake.bronze_gb.raw_events_multiline`
    — plain bin-packing, no `CLUSTER BY`/`ZORDER` (this table isn't
    clustered; `8.3` tests compaction on its own, distinct from `8.2`/`8.2b`).
  - *Expected output / observed:*
    - Before: **4,000 rows, 20 files read, 219,241,796 bytes read (~209 MB,
      nearly the whole 222 MB table — expected, no predicate means no
      data-skipping is possible either way), 7,777 ms.**
    - `OPTIMIZE` returned `numFilesAdded: 4, numFilesRemoved: 20` — a real
      compaction, 20 small files merged into 4 larger ones
      (`sizeInBytes` 222,287,073 → 208,346,802, slightly smaller from better
      compression at larger file sizes).
    - After: **4,000 rows (same), 4 files read, 202,334,925 bytes read
      (~193 MB), 3,120 ms.**
  - *Validation check:* `DESCRIBE DETAIL` before/after confirmed the
    physical file-count/size change; row count and the `sum(size(...))`
    aggregate value were identical before and after — correctness preserved,
    only physical layout changed.
  - **Conclusion — a real, causally-explainable improvement, unlike `8.2`'s
    cache artifact:** files read dropped 80% (20→4), bytes read dropped only
    7.7% (expected — no data-skipping applies to an unfiltered scan; the
    small byte reduction is just better Parquet compression at larger file
    sizes), and **duration dropped 60% (7,777 ms → 3,120 ms)**. Unlike `8.2`,
    where bytes/files were unchanged and the duration drop was pure cache
    warm-up, here both bytes *and* files genuinely changed — so there's a
    real physical mechanism to attribute the duration improvement to (fewer
    files means fewer file-open/close operations and less task-scheduling
    overhead across the scan), not just a coincidence of running the query
    twice.
  - **Contrast with `8.2`/`8.2b`, worth stating plainly:** clustering helps a
    *filtered* query by skipping files that don't match the predicate
    (`8.2b`: files 8→1, bytes ~89% down). Compaction helps a *full-scan*
    query by reducing per-file overhead (`8.3`: files 80% down, bytes barely
    move, duration 60% down). Same general shape of test, two genuinely
    different mechanisms — tell them apart by which of bytes/files moves
    most in the result.

- **Step 8.4 — Join strategy**
  - *Objective:* confirm SQL join hints are honored on serverless (a live
    check the plan flagged as unverified), then measure the real cost of
    forcing a non-default join strategy against Spark's own default choice,
    on two genuinely different scenarios.
  - *Concept:* Spark auto-broadcasts a small dimension by default; the more
    informative test is a large-large join where Spark must choose between
    shuffle-based strategies organically — the small-dim case is "somewhat
    degenerate" (per the plan's own wording) since Spark already picks the
    right plan without help.

  **Part A — small-dim: `fct_transactions` (2.1M rows) × `dim_merchants`
  (100 rows) on `merchant_id`.**
  - *Task:* `EXPLAIN` the unhinted query (confirms Spark's default), then
    the same query with `/*+ SHUFFLE_HASH(m) */` and `/*+ MERGE(m) */`.
  - *Observed:* default → `PhotonBroadcastHashJoin` (as expected). `/*+
    SHUFFLE_HASH(m) */` → `PhotonShuffledHashJoin`, still fully Photon.
    `/*+ MERGE(m) */` → real `SortMergeJoin` — **and Photon explicitly
    declines to run it** ("Photon does not fully support the query...
    Unsupported node: SortMergeJoin"), falling back to classic row-based
    Spark for the join itself. All three hints confirmed honored — the
    plan's flagged live check is answered.
  - **Measurement detour, a real methodology finding in its own right:**
    the first attempt at measuring all three (separate stateless calls, each
    preceded by its own `SET use_cached_result = false`) came back with
    `read_bytes/read_files = 0` for both hinted variants, despite each
    query's own `EXPLAIN` showing a real `PhotonScan`. Checked
    `system.query.history`'s `from_result_cache`/`cache_origin_statement_id`
    directly rather than assuming: both hinted queries had been served from
    the **default query's cached result** — Databricks' cache matched on
    logical equivalence (same tables/predicate/output), ignoring that the
    hint changes physical execution, and the per-call `SET` never took
    effect because each call is its own stateless session. Fixed by creating
    an explicit session (`POST /api/2.0/sql/sessions`) and reusing its
    `session_id` for `SET` + each query.
  - *Final, cache-verified, same-warm-session results* (`count(*)` wrapper,
    identical correctness check: all three return 2,111,585):

    | Strategy | Files | Bytes read | Duration |
    |---|---|---|---|
    | Default (broadcast) | 3 | 2,467,304 | 888 ms |
    | `SHUFFLE_HASH` | 3 | 2,467,304 | 1,083 ms (+22%) |
    | `MERGE` (`SortMergeJoin`) | 3 | 2,467,304 | 2,095 ms (+136%) |

    Bytes/files are **identical across all three** — expected and correct
    for a join-strategy test (unlike `8.2`/`8.3`): the scan side doesn't
    change, only how the join executes. The cost shows entirely in duration:
    default was already optimal; `SHUFFLE_HASH` adds real but modest
    overhead; `MERGE` is markedly worse, compounded by the Photon fallback.

  **Part B — large-large: `int_events_deduped` (3,200,000 rows) ×
  `int_transactions` (1,439,742 rows) on `event_id`.**
  - *Task:* `EXPLAIN` the unhinted query first — does Spark pick
    `SortMergeJoin` organically at this scale, or something else?
  - *Observed:* Spark's own default here is `PhotonShuffledHashJoin`, not
    `SortMergeJoin` — `int_transactions` (1.44M rows) is still small enough
    to build an in-memory hash table after shuffling. Forced a genuine
    `SortMergeJoin` via `/*+ MERGE(t) */`, confirmed via `EXPLAIN` (same
    Photon-fallback pattern as Part A).
  - **First measurement attempt was misleading again**, same lesson as
    `8.2`: the un-hinted default ran first in a brand-new session and showed
    6,591 ms, while the *second* query in that session (`MERGE`) showed only
    2,450 ms — looking like `MERGE` won. Re-measured the default warm, in the
    same session, before trusting this.
  - *Final, cache-verified, fully-warm results* (correctness check: both
    return 1,439,742 rows, matching `int_transactions` exactly — no orphans,
    as expected since it's derived from `int_events_deduped` by filter):

    | Strategy | Rows scanned | Bytes read | Files | Shuffle (network) | Duration |
    |---|---|---|---|---|---|
    | Default (`ShuffledHashJoin`) | 4,639,742 | 83,758,091 (~80 MB) | 10 | 0 | 1,311 ms |
    | `MERGE` (`SortMergeJoin`) | 4,639,742 | 83,758,091 (~80 MB) | 10 | 0 | 2,038 ms |

    Same direction as Part A (`SortMergeJoin` slower), a smaller relative
    penalty this time (+55% vs. +136%) — at larger scale, more of the total
    time is genuine shared I/O/shuffle work common to both strategies, so
    the Photon-fallback penalty matters proportionally less.
  - **`shuffle_read_bytes` stayed exactly 0 in both parts**, despite Part
    B's real 80 MB, 16-way-partitioned shuffle — see §4's concept note; this
    is read as a genuine platform signal (few-node serverless warehouse,
    shuffle stays local), not a metric-collection gap.
  - **Conclusion:** Spark's own default join selection was correct in both
    scenarios tested here — broadcasting a small dimension, and
    shuffle-hash-joining two large-but-not-both-huge tables. Forcing a
    non-default strategy (`SHUFFLE_HASH` or `MERGE`) never won; `MERGE`
    specifically costs the most, compounded by a real Photon-acceleration
    loss on this platform, not just theoretical shuffle/sort overhead.

- **Steps 8.5–8.6** — not yet reached.

## 7. Operational Considerations
- Idempotency / re-run safety: `ALTER TABLE ... CLUSTER BY` and `OPTIMIZE`
  are both safe to re-run — `OPTIMIZE` is a no-op once a table is already
  compacted/clustered, and re-running it against `fct_transactions` right now
  would again report `numFilesAdded: 0` for the same reason.
- Performance (the whole point of this module): see `8.1`/`8.2`/`8.3` above.
  Measurement methodology going forward: wall-clock/rows via the fast Query
  History API immediately after each query; full bytes/files via a polling
  loop against `system.query.history` (30s interval, no fixed attempt count
  assumed — freshness has no SLA); `SET use_cached_result = false` at the
  start of every before/after session, and a query shape confirmed via
  `EXPLAIN` to produce a real `PhotonScan` (not `LocalTableScan`) before
  trusting any comparison.
- **Predictive Optimization is live on this workspace.** Check
  `system.storage.predictive_optimization_operations_history` for a
  candidate table before any `8.x` before/after test, and act promptly once
  a clean "before" state is confirmed — PO could compact/cluster a table in
  the background at any time, and it leaves no trace in `SHOW TBLPROPERTIES`.
- **Standard measurement protocol from `8.4` onward:** create an explicit
  SQL session (`POST /api/2.0/sql/sessions`), run `SET use_cached_result =
  false` in it, then run every variant being compared (including a warm
  re-measurement of "default"/"before") within that same `session_id` —
  a bare per-call `SET` without a shared session does nothing, and the
  result cache matches on logical equivalence, not literal query text, so
  even uniquely-aliased queries can share a cached result silently.

## 8. Data Quality & Governance
- No new physical tables created by `8.1`/`8.2` (per ADR-0011's table-quota
  addendum) — `ALTER TABLE`/`OPTIMIZE` both modify `fct_transactions` in
  place.
- `8.2b` did create one scratch table
  (`gold_gb._scratch_fct_transactions_clustering_test`), per ADR-0011's own
  named exception (an experiment doc explicitly justifying it, gated, dropped
  immediately after the comparison completes) — confirmed dropped, zero
  lasting footprint on the table-quota budget.

## 9. Validation & Acceptance Criteria
- [x] `8.1` baseline captured with a validated-clean starting state (no
      background confounders)
- [x] `8.2` liquid clustering: config change confirmed applied
      (`clusteringColumns`), physical effect (or lack thereof) confirmed via
      `OPTIMIZE` metrics + `DESCRIBE DETAIL` diff, not assumed from duration
      alone
- [x] `8.2b`: clustering's real data-skipping effect directly observed on a
      disposable scratch copy once past the file-count threshold (files 8→1,
      bytes ~118 MB→~12.9 MB), scratch table confirmed dropped after
- [x] `8.3`: genuine fragmentation found via survey (not artificial), a real
      compaction confirmed via `OPTIMIZE`'s own metrics and `DESCRIBE DETAIL`
      diff (files 20→4), a real and causally-explained duration improvement
      (60%, unlike `8.2`'s cache artifact) — Predictive Optimization activity
      checked and accounted for before trusting the comparison
- [x] `8.4`: join hints confirmed honored via `EXPLAIN` on both a small-dim
      and a large-large join; a real result-cache confound (matching on
      logical equivalence, not query text) found and fixed via an explicit
      session; cold-start effects caught and re-measured warm in both parts;
      `SortMergeJoin`'s Photon fallback and cost confirmed at two scales
- [ ] `8.5`–`8.6`: not yet run
- [ ] All six ADR-0008 techniques have a recorded before/after result
- [ ] `README.md` roadmap/Status updated; `v0.9` tagged — final steps, not yet
      reached

## 10. Key Takeaways
- A config change (`ALTER TABLE ... CLUSTER BY`) and a physical effect
  (`OPTIMIZE` actually rewriting files) are two different things — verify the
  second via `OPTIMIZE`'s own metrics, never assume it from the first alone.
- Duration deltas are not reliable evidence of an I/O-level optimization
  without also checking bytes/files scanned — caching effects can produce a
  large, entirely real duration improvement with zero underlying change.
- When clustering *does* get a real chance to work (enough files to
  reorganize), the effect is large and clean: 87.5% fewer files read, 89%
  fewer bytes read for the same query, same rows, same result — confirmed
  directly on a scratch copy, not just theorized from documentation.
- Bin-packing `OPTIMIZE` merges small files; it never splits large ones —
  a lower `delta.targetFileSize` alone does nothing to an already-large file.
- Compaction and clustering fix different problems and show up differently
  in a before/after: compaction (`8.3`) barely moves bytes for a full scan
  but cuts duration a lot (less per-file overhead); clustering (`8.2b`) cuts
  both bytes and files a lot for a filtered query (data-skipping). Reading
  which metric actually moved tells you which mechanism is really at work.
- Two confounds can silently invalidate a before/after comparison before
  clustering/compaction ever enters the picture: Delta answering a query
  from metadata alone (`LocalTableScan`, zero bytes read) and the query
  result cache returning a stale-but-identical result. Check `EXPLAIN` for a
  real `PhotonScan` and disable `use_cached_result` before trusting any
  number.
- Predictive Optimization is genuinely active on this workspace and
  invisible to `SHOW TBLPROPERTIES` — the only real evidence is
  `system.storage.predictive_optimization_operations_history`. Check it, and
  move promptly once a clean "before" state is confirmed.
- Spark's default join selection (broadcast for a small dim, shuffle-hash
  for two large-but-not-huge tables) was correct in both cases tested here —
  forcing a different strategy never won, and forcing `SortMergeJoin`
  specifically costs the most because it also falls out of Photon
  acceleration on this platform, not just from extra sort/shuffle work.
- The result cache matches on logical result equivalence, not literal SQL
  text — a join hint alone won't bust it, and neither will a unique alias.
  The only fix found: an explicit session (`POST /api/2.0/sql/sessions`)
  reused across `SET` and each query being compared.
- `shuffle_read_bytes = 0` on a real shuffle is a platform signal (shuffle
  stays local on this workspace's few-node serverless warehouse), not a
  broken metric — confirmed at two different scales.

## 11. Knowledge Check
- Q1: Why did `OPTIMIZE` report `numFilesAdded: 0` even though it ran
  successfully against a freshly-clustered table?
- Q2: `fct_transactions`'s query got 86% faster after clustering, but the
  bytes/files read didn't change. What's the most likely explanation, and
  why isn't "clustering worked" the right conclusion here?
- Q3: Setting `delta.targetFileSize` to a smaller value and running
  `OPTIMIZE` didn't fragment the scratch table. What did work instead, and
  why doesn't lowering the target alone force a split?
- Q4: On the scratch table, files read dropped 87.5% and bytes read dropped
  89%, but duration only improved 11%. What does that gap tell you about
  what wall-clock time is actually measuring at this data scale?
- Q5: `8.3`'s first candidate query (`count(*)`, `max(pagination.page)`)
  showed `LocalTableScan` in its plan even with the result cache disabled.
  Why didn't disabling the cache fix it, and what kind of query would?
- Q6: `8.3` showed files drop 80% but bytes drop only 7.7%, while `8.2b`
  showed both files *and* bytes drop by roughly the same large amount. What
  does that difference tell you about which optimization — compaction or
  clustering — actually ran in each case, without being told directly?
- Q7: Two hinted queries in `8.4` came back with `read_bytes = 0` and
  `read_files = 0` even though their own `EXPLAIN` plans showed real
  `PhotonScan` nodes. What actually happened, and why didn't `SET
  use_cached_result = false` prevent it?
- Q8: In the large-large join test, the first (unhinted) query showed
  6,591 ms and the forced `MERGE` query showed only 2,450 ms — making
  `MERGE` look faster. What was actually wrong with that comparison, and
  what did re-measuring reveal?
- Q9: Forcing `MERGE` costs +136% at small scale but only +55% at large
  scale, even though both cases fall out of Photon the same way. Why would
  the same fallback cost a smaller *relative* penalty as the query gets
  bigger?
- Q10: `shuffle_read_bytes` read exactly 0 for an 80 MB, 4.6M-row,
  16-way-partitioned shuffle. Does that mean no shuffle happened? What does
  it actually tell you about this workspace's compute?

## 12. References
- Internal: [ADR-0008](adr/0008-novalake-terminus-and-cerberus-succession.md),
  [ADR-0009](adr/0009-agentic-integration-mcp-gated-review-then-act.md),
  [ADR-0011](adr/0011-gb-scale-data-regeneration.md), `docs/checkpoint.md`
  (2026-07-28 entries)
- Databricks docs: Liquid clustering, `OPTIMIZE`, Query History API,
  `system.query.history` (no documented freshness SLA — confirmed via
  Databricks Community, not the official docs, which don't state a number
  either way)

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-28 | Module created; `8.1` (baseline) and `8.2` (liquid clustering, a clean null result) documented | Chirag + Claude |
| 2026-07-28 | `8.2b` added: empirical verification of `8.2`'s null result on a disposable scratch copy, forced past the file-count threshold — real clustering effect confirmed directly (files 8→1, bytes ~118 MB→~12.9 MB), plus a found-live sub-finding that bin-packing `OPTIMIZE` doesn't split large files | Chirag + Claude |
| 2026-07-28 | `8.3` added: `OPTIMIZE`/file compaction on a genuinely fragmented table (`bronze_gb.raw_events_multiline`, 20 files). Found and fixed two real methodology confounds first (Delta metadata-only query answering, query result caching) and confirmed Predictive Optimization is genuinely active on this workspace (invisible to `SHOW TBLPROPERTIES`, visible in `system.storage.predictive_optimization_operations_history`). Real, causally-explained result: files 20→4, duration −60%, contrasted directly with `8.2`'s cache-artifact duration drop | Chirag + Claude |
| 2026-07-28 | `8.4` added: join strategy, both a small-dim (`fct_transactions` × `dim_merchants`) and a large-large (`int_events_deduped` × `int_transactions`) test. Confirmed join hints are honored and that forcing `SortMergeJoin` falls out of Photon entirely. Found and fixed a genuine result-cache confound (matches on logical equivalence, not query text — fixed via an explicit session) and caught cold-start effects in both parts before trusting any comparison. Spark's own default join choice won in both scenarios; `shuffle_read_bytes` stayed 0 at both scales, read as a real platform signal | Chirag + Claude |
