# Module 9 · Spark Optimization (Serverless-Constrained)

`Status:` Draft — GB-scale full run complete and validated (2026-07-28);
`§8` optimization experiments in progress (8.1, 8.2, 8.2b done) ·
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
- [ ] `8.3`–`8.6` objectives — not yet reached

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

## 5. Data Contract / Schema in Scope
- `novalake.gold_gb.fct_transactions` — 2,138,809 rows, 21 columns, unclustered
  at experiment start (`clusteringColumns: []`, `clusterByAuto: false`,
  2 files, 123,263,770 bytes total)
- Representative query used throughout `8.1`/`8.2`:
  `SELECT * FROM gold_gb.fct_transactions WHERE merchant_id = 'mer_1050'`
  (`mer_1050` is a non-skewed merchant — 8,525 matching rows, ~0.4% of the
  table, consistent with ADR-0011's skew design where only `mer_1000`/
  `mer_1001` are deliberately hot)

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

- **Steps 8.3–8.6** — not yet reached.

## 7. Operational Considerations
- Idempotency / re-run safety: `ALTER TABLE ... CLUSTER BY` and `OPTIMIZE`
  are both safe to re-run — `OPTIMIZE` is a no-op once a table is already
  compacted/clustered, and re-running it against `fct_transactions` right now
  would again report `numFilesAdded: 0` for the same reason.
- Performance (the whole point of this module): see `8.1`/`8.2` above.
  Measurement methodology going forward: wall-clock/rows via the fast Query
  History API immediately after each query; full bytes/files via a polling
  loop against `system.query.history` (30s interval, no fixed attempt count
  assumed — freshness has no SLA).

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
- [ ] `8.3`–`8.6`: not yet run
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
