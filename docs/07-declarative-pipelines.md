# Module 7 · Declarative Pipelines (DLT vs. dbt Comparison)

`Status:` Complete — build, validation, and Experiment 2 all done ·
`Owner:` Chirag · `Last updated:` v0.7 (module complete, 2026-07-27) ·
`Est. time:` ~1 day

**Scope decision (recorded formally in [ADR-0010](adr/0010-v0.7-silver-not-gold-comparison-target.md),
not silently redefined here):** ADR-0002 originally scoped this module as
"re-implement part of **Gold** with Declarative Pipelines... and compare the
two directly." Planning surfaced that Gold is mostly plain `GROUP BY`
aggregation SQL — a DLT materialized view doing the same aggregation looks
nearly identical to the existing dbt model, producing little to actually
compare. This module instead targets **Silver**: the `transaction.*`/ndjson
slice `stg_raw_events → int_events_deduped → int_transactions →
int_transactions_clean`/`int_transactions_dlq` — the same slice
`docs/02-silver.md` names as the original Silver proof-of-concept. Its output
already feeds `gold.fct_transactions`, giving a known-good downstream to
cross-check against without also building a DLT Gold layer. This plan went
through two Opus review passes before execution — see
`docs/adr/0010-v0.7-silver-not-gold-comparison-target.md` and this file's
Changelog for what each pass changed.

## 1. Learning Objectives
- [x] Can explain, with a live counter-example, why "DLT accepted this
      pattern" is not the same claim as "DLT correctly executed this logic" —
      and specifically why an unbounded `ROW_NUMBER()` ranking window is
      *rejected outright* on a Declarative Pipelines streaming table, not
      silently scoped to per-microbatch semantics
- [x] Can name the concrete mechanical difference between `EXPECT ... ON
      VIOLATION DROP ROW` and dbt's `_clean`/`_dlq` two-model pattern for
      quarantining bad rows, and why one of them (not both) leaves an
      inspectable trail of *which rows* were rejected
- [x] Can state, from an actual triggered violation (not documentation
      alone), whether a dropped row's content is recoverable from the DLT
      pipeline event log — **confirmed live: no.** The event log's
      `data_quality.expectations` exposes only an aggregate count
      (`failed_records`); the scratch table itself contains exactly the
      passing rows, nothing from the 150 dropped ones. See §6 Step 7.6.
- [x] Can explain why `Auto Loader`'s `STREAM read_files()` structurally
      cannot target a single literal file, even an unambiguous one, and what
      minimal fix (a one-character glob) restores the original intent
      (ingest exactly one of two sibling files in a flat landing volume)
      without ingesting both
- [x] Can identify a genuine `EXPECT`-expressiveness gap (row-uniqueness) that
      has no DLT equivalent at all, versus a gap that's just missing
      configuration

## 2. Prerequisites
- Completed modules: `v0.1` (Bronze, dbt), `v0.2` (Silver, dbt) — this module
  mirrors `int_events_deduped.sql`/`int_transactions.sql`/
  `int_transactions_clean.sql`/`int_transactions_dlq.sql` exactly, read in
  full before writing any DLT SQL.
- Tables / assets that must already exist: `novalake.bronze.raw_events`,
  `novalake.silver.int_events_deduped`, `int_transactions`,
  `int_transactions_clean`, `int_transactions_dlq`, `novalake.gold.fct_transactions`
  (used read-only as a downstream cross-check, not rebuilt).
- Compute / cluster config: serverless DLT pipeline compute (`serverless:
  true`, `edition: ADVANCED`) — availability was not pre-assumed; deploying
  and running the minimal Bronze flow was itself the live availability
  check, per the same "verify, don't assume" discipline `v0.6` Step 6.3 used
  for Vector Search endpoint creation.

## 3. Where This Fits (Architecture Context)
- One-line: an independent, parallel-schema re-implementation of one Silver
  slice, built to compare against the existing dbt implementation directly —
  not a replacement, not wired into the medallion job (`resources/dbt_job.yml`).
- Inputs → this module → Outputs: `novalake.bronze.landing`
  (`payments_events.json`, read a second time, independently) →
  DLT pipeline (`novalake_dlt_transactions`) → `novalake.bronze_dlt.raw_events`,
  `novalake.silver_dlt.{events_deduped,transactions,transactions_clean,transactions_dlq}`.
  `novalake.gold.fct_transactions` is read, never written, as a validation
  anchor.

## 4. Concepts & Background
- **Streaming table vs. materialized view**: a streaming table processes new
  input incrementally (`STREAM read_files(...)`, Auto Loader); a materialized
  view recomputes from its full source on refresh. This module deliberately
  tested the boundary between the two rather than assuming it from
  documentation — see §6 and §9.
- **Declarative expectations (`EXPECT`)**: inline row-level constraints with
  three violation actions — implicit warn (log, keep the row), `ON VIOLATION
  DROP ROW` (silently discard), `ON VIOLATION FAIL UPDATE` (abort the whole
  update). None of the three, on their own, gives an *inspectable* quarantine
  the way dbt's `_dlq` model does — see §8.
- **Pipeline edition**: `CORE` rejects any `EXPECT` at all; `ADVANCED` is
  required whenever `EXPECT` is used, independent of CDC; `PRO` is what
  `AUTO CDC INTO`/SCD needs (not used in this module). Confirmed live, not
  just from docs — the pipeline's `edition: ADVANCED` on serverless compute
  was accepted (the run got well past config validation into per-flow
  execution before failing on unrelated grounds).
- **Common pitfalls hit this build**: `STREAM read_files()` requires a
  directory-resolvable path, not a literal filename (§6); DLT will not change
  a table's declared dataset type (`STREAMING_TABLE` ↔ `MATERIALIZED_VIEW`)
  in place once registered, even with zero rows written (§6); Free Edition's
  daily compute quota is a real, hard, account-wide ceiling that also blocks
  the SQL warehouse once hit, not just new pipeline compute (§9).

## 5. Data Contract / Schema in Scope
- Source schema (expected): `novalake.bronze.landing` volume,
  `payments_events.json` (ndjson, flat file, sibling to
  `payments_events_multiline.json` which this module does not ingest).
- Target schema (produced): `novalake.bronze_dlt.raw_events` (10-plus-metadata
  columns, matches `novalake.bronze.raw_events`'s core columns plus DLT's own
  `_rescued_data`); `novalake.silver_dlt.events_deduped` (14 columns, matches
  `int_events_deduped.sql`); `novalake.silver_dlt.transactions`/
  `transactions_clean`/`transactions_dlq` (25 columns each, matches
  `int_transactions.sql`/`int_transactions_clean.sql`/`int_transactions_dlq.sql`).
- Schema-evolution policy: `schemaHints` pins the four columns known to be
  ambiguously-typed across schema versions (`payload.risk`,
  `payload.amount_minor`, `event_timestamp`, `ingested_at`) to `STRING` —
  matching what the original batch `spark.read.json()` happened to infer, so
  the same `from_json`/`try_cast` drift-resolution logic downstream works
  unchanged. No other evolution handling; this is a bounded, static dataset
  (see §7).
- Keys / grain / uniqueness: one row per `event_id` after `events_deduped`
  (7,000 unique event_ids from 7,105 raw rows — 105 replayed duplicates
  removed); `transactions` scoped to `transaction.{completed,failed,created}`
  only (3,192 rows); `transactions_clean`/`transactions_dlq` exhaustively and
  exclusively partition `transactions` on `event_timestamp_quality` (3,042 +
  150 = 3,192).

## 6. Step-by-Step Implementation

- **Step 7.1 — Record the ADR-0002 scope deviation**
  - *Objective:* formally record the Gold→Silver comparison-target change
    before writing any pipeline code, per this project's "corrections get a
    new ADR, not a silent edit" convention.
  - *Task:* authored `docs/adr/0010-v0.7-silver-not-gold-comparison-target.md`;
    added a `Status` note to ADR-0002 pointing at it; added ADR-0010 to
    `docs/adr/README.md`'s index.
  - *Validation check:* `docs/adr/0002-...md`'s Status line reads "Accepted —
    partially superseded by ADR-0010"; ADR-0010 exists with full Context/
    Decision/Consequences/Alternatives.

- **Step 7.2 — Write the pipeline SQL (5 files)**
  - *Objective:* mirror the four dbt models 1:1 in DLT SQL, schema-qualified
    against parallel target schemas.
  - *Task:* `pipelines/transformations/bronze/raw_events.sql`,
    `pipelines/transformations/silver/{events_deduped,transactions,
    transactions_clean,transactions_dlq}.sql`.
  - *Concept:* every Silver DDL is fully schema-qualified
    (`novalake.silver_dlt.<table>`) rather than relying on the pipeline's
    declared default schema (`bronze_dlt`) — a gap the second plan-review
    pass caught before any code was written.
  - *Validation check:* `databricks bundle validate` passes; SQL mirrors the
    dbt originals' column lists and macro logic (`clean_currency`/
    `clean_country` inlined verbatim).

- **Step 7.3 — Write and deploy `resources/dlt_pipeline.yml`**
  - *Objective:* a DAB-managed serverless pipeline resource, isolated from
    the existing `dbt_job`/Vector Search/dashboard resources.
  - *Task:* `catalog`/`schema: bronze_dlt`/`serverless: true`/`edition:
    ADVANCED`/`channel: CURRENT`/`continuous: false`/`libraries.glob.include`/
    `event_log` (catalog/schema/name, confirmed required together via
    `databricks bundle schema`)/`configuration` (namespaced `novalake.catalog`
    key, `spark.sql.session.timeZone: UTC`).
  - *Validation check:* `databricks bundle plan --select
    pipelines.novalake_dlt_transactions` showed exactly `create
    pipelines.novalake_dlt_transactions`, `1 to add, 0 to change, 0 to
    delete` — nothing else in the bundle touched.

- **Step 7.4 — Deploy and run (gated, ADR-0009)**
  - *Objective:* the live serverless-DLT availability check, doubling as the
    real deploy.
  - *Task:* `databricks bundle deploy --select pipelines.novalake_dlt_transactions
    --fail-on-active-runs` then `databricks bundle run novalake_dlt_transactions`.
    Presented exact commands and named side effects (schema auto-create)
    before running, per ADR-0009; every gated step logged to
    `docs/checkpoint.md`'s revisit log (2026-07-27 entries).
  - **Live finding 1 — Auto Loader rejects a literal file path.** First run
    failed immediately: `Input path .../payments_events.json is not a
    directory`. The original plan's assumption — point `STREAM read_files()`
    directly at the one ndjson file to avoid the sibling multiline file —
    was wrong: Auto Loader's streaming listener structurally requires a
    directory-resolvable path. **Fix:** a one-character bracket-class glob,
    `payments_events[.]json` — functionally an exact match on the same single
    filename, but syntactically contains glob metacharacters, so the path
    resolves as "directory with filter" instead of "literal file, rejected."
  - **Live finding 2 — Experiment 1 result: DLT rejects the streaming
    `ROW_NUMBER` dedup pattern.** `events_deduped.sql`, first attempted as a
    `CREATE OR REFRESH STREAMING TABLE` with `ROW_NUMBER() OVER (PARTITION BY
    event_id ORDER BY ...)` (matching the DLT skill's own canonical dedup
    example), failed on deploy:
    ```
    [NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING] Window function is not
    supported in ROW_NUMBER() (as column `rn`) on streaming DataFrames/
    Datasets. Structured Streaming only supports time-window aggregation
    using the WINDOW function.
    ```
    This **resolves, live, a genuine conflict** the plan flagged between the
    bundled DLT skill's own documented example and the general Spark
    Structured Streaming rule that non-time-bounded ranking windows are
    invalid on streaming DataFrames — the general rule wins; the skill's
    example does not hold for this exact construction. **This is a clean
    rejection, not an ambiguous "accepted but maybe wrong" result** — the
    more informative of the two outcomes the plan anticipated, since it
    avoids the harder problem of having to caveat an accepted-but-unverified
    per-microbatch dedup semantic. Fell back to `MATERIALIZED VIEW`, the
    plan's pre-committed fallback, cascading to a plain (non-`STREAM`) read
    in every downstream file.
  - **Live finding 3 — dataset type is immutable once registered, even
    empty.** Redeploying the `MATERIALIZED VIEW` fallback failed again:
    `[CANNOT_CHANGE_DATASET_TYPE] Cannot change the dataset type of a
    pipeline table from STREAMING_TABLE to MATERIALIZED_VIEW ... To change
    the dataset type, please drop the existing dataset first` — even though
    the first (failed) attempt never wrote a single row. Presented `DROP
    TABLE novalake.silver_dlt.events_deduped` as its own named gated action
    (per this project's amended gated-action list) and got explicit go-ahead;
    executed via `execute_sql`. Redeploy + run then succeeded end to end —
    all five flows `COMPLETED`.
  - *Validation check:* `databricks bundle run` output shows every flow
    (`raw_events`, `events_deduped`, `transactions`, `transactions_clean`,
    `transactions_dlq`) reaching `COMPLETED`; `update_progress` reaches
    `COMPLETED`.

- **Step 7.5 — Validate (row-count, content, and expectation parity)**
  - *Objective:* prove the DLT output matches the dbt original exactly, not
    just approximately.
  - *Task:* see §9 for the full results table.
  - *Validation check:* all green — see §9.

- **Step 7.6 — Experiment 2: DLQ event-log recoverability (complete)**
  - *Objective:* empirically confirm — not just cite documentation — whether
    a dropped row's content is recoverable from the DLT event log after an
    `EXPECT ... ON VIOLATION DROP ROW` violation.
  - *Task:* presented and got go-ahead for a scratch table
    (`novalake.silver_dlt._scratch_dlq_test`, `CONSTRAINT test_drop EXPECT
    (event_timestamp_quality = 'ok') ON VIOLATION DROP ROW`, a predicate with
    a confirmed-live 150-row violation count). First attempt (same session
    the row-count/content parity checks were run) deployed successfully but
    the triggered run failed immediately with `RESOURCE_EXHAUSTED: ... you
    have hit your free daily limit` — confirmed account-wide, not
    pipeline-specific, since the SQL warehouse itself began rejecting
    ordinary `execute_sql` queries with the same underlying cause
    immediately after. Deferred; scratch file removed, pipeline redeployed
    without it in the interim.
  - **Result, once the daily quota reset (later session, same day)**:
    recreated the scratch file, redeployed, and reran. The flow completed
    (`novalake.silver_dlt._scratch_dlq_test` reached `COMPLETED`,
    `num_output_rows: 3042`). The event log's `data_quality.expectations`
    for this flow reported exactly:
    ```
    {"name": "test_drop", "dataset": "novalake.silver_dlt._scratch_dlq_test",
     "passed_records": 3042, "failed_records": 150}
    ```
    — an aggregate count only, no row-level fields anywhere in the event
    payload (no `event_id`, no dropped-row content, no sample). Cross-checked
    directly against the scratch table itself:
    `SELECT count(*) FROM novalake.silver_dlt._scratch_dlq_test` returned
    exactly 3,042, all with `event_timestamp_quality = 'ok'` — the 150
    dropped rows are genuinely gone, not retained anywhere queryable.
    **Conclusion, now empirically confirmed rather than documentation-sourced:
    `EXPECT ... ON VIOLATION DROP ROW` cannot produce an inspectable DLQ.**
    dbt's `_clean`/`_dlq` two-model `WHERE`-split — mechanically
    unglamorous, but genuinely doing something DLT's own headline
    expectation primitive cannot — is confirmed necessary, not just
    convention. Cleanup: `DROP TABLE
    novalake.silver_dlt._scratch_dlq_test` (gated, executed), scratch file
    removed from the repo, pipeline redeployed clean.

## 7. Operational Considerations
- Idempotency / re-run safety: streaming ingestion (`raw_events`) is
  checkpoint-based, safe to re-trigger; materialized views fully recompute on
  refresh, also safe to re-trigger, at the cost of a full rescan each time
  (acceptable at this data volume — 7,105 rows).
- Incremental vs. full refresh: **honest limitation, by design, not an
  oversight.** This is a static, single-batch synthetic dataset — there was
  never a second incoming wave to exercise genuine incremental/streaming
  pickup. `raw_events` is a streaming table (Auto Loader, technically
  incremental), but nothing in this build demonstrates cross-batch behavior.
  `events_deduped` ended up a materialized view (full recompute) specifically
  *because* the streaming dedup attempt was rejected (Step 7.4, Live finding
  2) — so even the one place this module could have shown a real incremental
  differentiator didn't survive contact with DLT's actual constraints. This
  was a deliberate scope decision going in (see ADR-0010's Alternatives and
  this project's plan discussion), not discovered as a limitation after the
  fact.
- Performance (partitioning / clustering / file sizing): not tuned — dataset
  size (7K/3K rows) makes this a non-issue for this module; not a
  representative signal either way.
- Failure & retry behaviour: DLT retries a failed flow automatically up to a
  platform-defined limit before marking it permanently failed (observed:
  `events_deduped` "has FAILED more than 0 times and will not be restarted"
  after its single deterministic `NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`
  failure — a semantic error doesn't benefit from retrying, and DLT didn't
  retry it blindly).

## 8. Data Quality & Governance
- Expectations / rules applied: `raw_events` — `has_event_id` (not-null,
  implicit warn). `transactions` — `customer_id_present`/`amount_present`/
  `risk_score_present`/`resolved_ts_present_when_ok` (all `FAIL UPDATE`),
  `currency_known` (implicit warn, the direct DLT analog of dbt's `severity:
  warn` `accepted_values` test).
- Quarantine / reject handling: **the central finding of this module, now
  confirmed empirically, not just from documentation.**
  `EXPECT ... ON VIOLATION DROP ROW` was deliberately *not* used for the
  `transactions_clean`/`transactions_dlq` split — both the bundled DLT
  skill's own docs and Databricks' official docs state that dropped-row
  *content* is not recoverable from the event log, only aggregate violation
  counts per constraint. Experiment 2 (Step 7.6) triggered a real 150-row
  violation on a scratch table and confirmed exactly that: the event log's
  `data_quality.expectations` exposed only `{"passed_records": 3042,
  "failed_records": 150}` — no row-level content whatsoever — and the
  scratch table itself held only the 3,042 passing rows. The two-table
  `WHERE event_timestamp_quality = 'ok'` / `!= 'ok'` split — mechanically
  identical to dbt's `_clean`/`_dlq` pair — is confirmed as DLT's only way
  to get an inspectable quarantine; `EXPECT ... DROP ROW` genuinely cannot
  substitute for it.
- **Dedup-correctness gap, a genuine DLT capability gap, not a workaround
  needed:** dbt's `unique`+`not_null` test on `int_transactions.event_id` —
  the one test that actually validates the dedup step worked, not just
  downstream drift-resolution logic — has no `EXPECT` equivalent. `EXPECT`
  operates on scalar per-row predicates; row-uniqueness across a table is not
  expressible at that scope. This module's substitute: the row-count parity
  check (`events_deduped` 7,000 = 7,000) serves as an indirect proxy —
  a matching count against a known-deduplicated dbt table makes a duplicate
  `event_id` in the DLT output very unlikely, but this is not the same
  strength of guarantee as an explicit uniqueness constraint.
- Lineage & catalog tags: not configured this module — out of scope for a
  comparison exercise; both `bronze_dlt`/`silver_dlt` and `bronze`/`silver`
  are visible in Unity Catalog lineage via normal table read/write tracking.
- Ownership & access: no additional grants configured; deployed under
  Chirag's personal identity, same as every other `dev`-target resource.

## 9. Validation & Acceptance Criteria

**Row-count parity** (dbt vs. DLT, exact match on every layer):

| Layer | dbt | DLT | Match |
|---|---|---|---|
| bronze / raw_events | 7,105 | 7,105 | ✅ |
| events_deduped | 7,000 | 7,000 | ✅ |
| transactions | 3,192 | 3,192 | ✅ |
| transactions_clean | 3,042 | 3,042 | ✅ |
| transactions_dlq | 150 | 150 | ✅ |

- [x] Row-count / reconciliation check: exact match on all 5 layers (above).
- [x] Schema assertion: `novalake.bronze_dlt.raw_events` schema diff against
      `novalake.bronze.raw_events` — same core columns, `_rescued_data`
      DLT-only, `_rescued_data IS NOT NULL` count = 0 (no rows silently
      rescued due to schema-inference mismatch).
- [x] Business-rule assertion, expanded (11 columns, second Opus review's
      finding that the original plan's row-level parity check omitted
      `country_clean` — the highest-drift-risk column, a 4-branch macro):
      `amount_minor_resolved`, `currency_clean`, `country_clean`,
      `risk_score`, `risk_flagged`, `risk_malformed`, `status`,
      `idempotency_key`, `resolved_event_timestamp`, `resolved_source_system`
      — **0 mismatched rows** across all 3,042 `transactions_clean` rows.
- [x] Content-level Gold cross-check (corrected from a tautological
      count-only check in the second plan revision to an actual `event_id`
      join checking `merchant_id`/`status`/`country_clean`/
      `payment_method_type` against `gold.fct_transactions`): **0
      mismatches.**
- [x] DLQ exhaustive/exclusive invariant:
      `transactions_clean` (3,042) + `transactions_dlq` (150) =
      `transactions` (3,192). ✅
- [x] Warn-expectation proof, with a resolved grain discrepancy: the live
      pipeline event log's `data_quality.expectations` for `currency_known`
      reported 94 `failed_records`, not the plan's expected 90. Checked
      directly rather than assumed a bug — 94 is the correct count at the
      pre-DLQ-split `transactions` grain on **both** dbt
      (`silver.int_transactions`) and DLT (`silver_dlt.transactions`) sides
      identically; 90 is the `_clean`-only count, also identical on both
      sides. A grain-scoping clarification, not a discrepancy.
- [x] Experiment 2 (DLQ event-log row-content recoverability): **confirmed
      live — not recoverable.** Event log exposed only an aggregate count
      (`passed_records: 3042, failed_records: 150`); the scratch table
      contained exactly the 3,042 passing rows. See §6 Step 7.6.
- [x] Sign-off: green — all validation criteria met, ready to tag `v0.7`.

## 10. Key Takeaways
- Live testing surfaced three real build-time findings documentation alone
  didn't predict: `STREAM read_files()` can't target a literal file;
  `ROW_NUMBER()` on a streaming table is a hard rejection, not a silent
  weaker-guarantee acceptance (a cleaner, more useful outcome for this
  module's comparison goal than the plan's alternate scenario would have
  been); and a pipeline table's dataset type is immutable post-registration,
  even with zero rows written.
- Where the two tools produce genuinely different execution models for the
  same declared intent (dedup): dbt recomputes the full table every run;
  DLT's equivalent streaming construct is flatly unsupported for this exact
  logic, forcing a materialized-view fallback that's mechanically identical
  to dbt's own "recompute everything" approach — so, empirically, this
  specific DLT/dbt comparison converges on the *same* execution model rather
  than diverging, which is itself the finding, not a failure to find one.
- Where the two tools look nearly identical (`transactions.sql`'s payload
  drift resolution): confirmed as a deliberate negative result, not forced —
  `from_json`/`try_cast`/macro-equivalent-`CASE` translate almost verbatim.
- Where dbt's less "declarative-looking" pattern (`_clean`/`_dlq` two-model
  WHERE-split) turns out to be doing something DLT's own headline primitive
  (`EXPECT ... DROP ROW`) genuinely can't replace for this need — confirmed
  live via Experiment 2, not just cited from documentation: a triggered
  150-row violation left zero row-level trace anywhere queryable, only an
  aggregate count.

## 11. Knowledge Check
- Q1: Why does `ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY ...)`
  fail on a DLT streaming table with `NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`,
  and why would an *accepted* version of this same pattern (had DLT allowed
  it) still not have proven correctness on this module's dataset?
- Q2: What is the one Unity Catalog DDL fact this module discovered that
  makes "just fix the SQL and redeploy" not always sufficient when switching
  a table between `STREAMING TABLE` and `MATERIALIZED VIEW`?
- Q3: Why does the 94-vs-90 `currency_known` violation count NOT indicate a
  dbt/DLT mismatch, once the grain each number is computed at is made
  explicit?

## 12. References
- Internal: [ADR-0002](adr/0002-use-dbt-for-silver-gold.md),
  [ADR-0010](adr/0010-v0.7-silver-not-gold-comparison-target.md),
  [ADR-0009](adr/0009-agentic-integration-mcp-gated-review-then-act.md),
  `docs/checkpoint.md` (2026-07-27 entries), `docs/02-silver.md`,
  `.claude/skills/databricks-spark-declarative-pipelines/`
- Databricks docs: [Lakeflow Declarative Pipelines](https://docs.databricks.com/dlt/index.html),
  [read_files function reference](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files),
  [Pipeline expectations](https://docs.databricks.com/aws/en/dlt/expectations)

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-27 | Plan drafted (Gold-scoped, per ADR-0002 literal wording); first Opus review pass found 12 issues (edition requirements, streaming-table/MV rules, Bronze schema-inference risk, Gold timezone risk, missing Gold columns, missing model, unsafe `bundle deploy` sequencing, doc/DoD gaps) — all folded in. | Claude (Sonnet 5) + Opus 5 review |
| 2026-07-27 | Chirag brought in external pressure-testing feedback; scope redirected from Gold to Silver (ADR-0010); plan rewritten around the 4-model `transaction.*` slice, SQL-not-Python, no second data wave (build as streaming where possible, document the limitation honestly). | Chirag + Claude (Sonnet 5) |
| 2026-07-27 | Second Opus review pass (against the Silver-scoped revision) found 10 more issues — most significantly the unqualified Silver DDL (would've deployed into the wrong schema), the "acceptance ≠ correctness" gap in Experiment 1's framing, the ADR-0002 deviation belonging in a new ADR rather than `checkpoint.md`, a missed `schemaHints` column, an unguaranteed-violation scratch predicate, a missing dedup-uniqueness test mapping, a tautological Gold cross-check, and gated-action-list/`--select` gaps — all folded in before execution began. | Claude (Sonnet 5) + Opus 5 review |
| 2026-07-27 | ADR-0010 drafted and accepted; ADR-0002/`docs/adr/README.md` amended; `CLAUDE.md`/`CONTRIBUTING.md` gated-action/DoD lists amended; all 5 pipeline SQL files and `resources/dlt_pipeline.yml` written. | Claude (Sonnet 5) |
| 2026-07-27 | First deploy/run (gated, ADR-0009): hit and fixed the `read_files` literal-file-path rejection; Experiment 1 (streaming dedup) rejected live, fell back to materialized view; hit and fixed `CANNOT_CHANGE_DATASET_TYPE` via a gated `DROP TABLE`. Final run succeeded end to end. | Claude (Sonnet 5), gated actions approved by Chirag |
| 2026-07-27 | §9 validation run: exact row-count/content/expectation parity across every check; 94-vs-90 grain discrepancy investigated and resolved (not a bug). Experiment 2 (DLQ event-log recoverability) presented, approved, and deployed, but blocked at run time by Free Edition's daily compute quota (`RESOURCE_EXHAUSTED`) — confirmed account-wide via the SQL warehouse also failing; deferred. Module left untagged pending this one open item. | Claude (Sonnet 5), gated action approved by Chirag |
| 2026-07-27 | **Experiment 2 completed once the daily quota reset, same day.** Recreated the scratch table, redeployed, reran — flow `COMPLETED`. Confirmed empirically: the event log's `data_quality.expectations` exposes only an aggregate count (`passed_records: 3042, failed_records: 150`), no row-level content; the scratch table itself held exactly the 3,042 passing rows. `EXPECT ... ON VIOLATION DROP ROW` cannot produce an inspectable DLQ — dbt's `_clean`/`_dlq` split is confirmed necessary, not just conventional. Cleaned up (`DROP TABLE`, gated; scratch file removed; pipeline redeployed clean). Module status: Complete, all validation criteria green, ready to tag. | Claude (Sonnet 5), gated actions approved by Chirag |
