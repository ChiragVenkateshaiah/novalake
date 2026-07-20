# Module 2 · Silver — Conform, Cleanse, Explode

`Status:` In Progress  ·  `Owner:` Chirag  ·  `Last updated:` v0.2 (partial)  ·  `Est. time:` ~2h so far

> **Scope of this module as it stands.** This covers `transaction.completed` /
> `.failed` / `.created` only — one event family, chosen because it alone exercises
> all 5 Silver problem categories named in `docs/01-bronze.md` §8. The remaining 7
> event types (`support.ticket`, `auth.session`, `review.submitted`,
> `refund.issued`, `kyc.verification`, `payout.scheduled`, `risk.alert`) and the
> multiline file (`payments_events_multiline.json`, not yet landed in Bronze at
> all) are **deferred**, not solved — flagged here, not silently dropped. This
> module is **not complete** and `v0.2` is **not tagged** until they land, per
> `CONTRIBUTING.md`'s per-module Definition of Done. Full design reasoning:
> `docs/plan.md`'s "v0.2 Silver — first slice" entry.

## 1. Learning Objectives
- [x] Can explain why envelope-level drift resolution (dedup, timestamp, source)
      is built generically across all event types while payload-level fixes stay
      scoped to one event family at a time
- [x] Can name which SQL construct fixes each of the 5 Silver problem categories:
      struct collapse → `from_json`, type-equivalent collapse → `try_cast`, key
      renaming → `coalesce`, structural reshaping → version-branched `case`, value
      dirtiness → `upper(trim(...))` / alias mapping
- [x] Can explain why `LATERAL VIEW OUTER posexplode` is the right choice when an
      array can be *both* genuinely empty *and* separately missing
- [ ] Can extend this same pattern to the remaining 7 event types (next slice —
      not done here)

## 2. Prerequisites
- Completed modules: `v0.0` (setup), `v0.1` (Bronze ingest into
  `novalake.bronze.raw_events`, DAB/dbt wiring, `stg_raw_events` pass-through)
- Tables/assets that must already exist: `novalake.bronze.raw_events` (7,105 rows),
  `src/dbt` project with `stg_raw_events` and its passing tests
- Compute: `dbt-databricks` locally against "Serverless Starter Warehouse"; DAB
  `dbt_task` on its own serverless `dbt_env` for orchestrated runs (unchanged
  from `v0.1`)

## 3. Where This Fits
- One-line: consumes Bronze's lossless raw envelope, produces conformed, deduped,
  drift-resolved, DLQ-split, exploded Silver models for `transaction.*`
- Inputs → this module → Outputs:
  `novalake.bronze.raw_events` → [`int_events_deduped` (generic, all event types)
  → `int_transactions` → `int_transactions_clean` / `int_transactions_dlq` →
  `int_transaction_line_items`] → `novalake.silver.*`
- `int_events_deduped` is the reusable generic layer every future event-type slice
  in this module builds on — it is *not* scoped to `transaction.*`, even though
  this slice only builds one payload-level consumer of it.

## 4. Concepts & Background
- **Generic vs. scoped layering.** Envelope fixes (dedup, timestamp, source) apply
  identically across all 10 event types — same shared JSON envelope shape — so
  building them once now avoids re-deriving the same logic 7 more times as the
  remaining event types get their own slices. Payload-level fixes genuinely do
  differ per event type and are *not* generalized prematurely.
- **Bronze's schema-collapse mechanism recurs.** `docs/01-bronze.md` documented it
  for `payload.risk` (a 3% string-vs-struct minority collapsed the whole column to
  STRING). The exact same mechanism applies to `event_timestamp` — v1 delivers
  epoch-millis ints, v2 delivers ISO strings, under the same JSON key, so the whole
  column infers to STRING regardless of which version produced any given row.
  Worth checking for on every new field touched, not just the ones already known
  to be dirty.
- **`staging/` vs `intermediate/`.** `models/staging/` stays a thin 1:1 source
  pass-through (dbt's own convention — that's all `stg_raw_events` does). Real
  cross-row/business logic (window functions, drift branching, explode) lives in
  the new `models/intermediate/` folder instead, still mapped to the same
  `novalake.silver` UC schema — a folder-organization distinction, not a schema one.
- **Pitfall caught before implementation, not after.** An early draft of the DLQ
  quality-flag logic risked comparing sentinel timestamps against the *raw*
  `event_timestamp` column instead of the resolved one — which would have silently
  missed every v1-encoded sentinel (~35% of defect rows, since v1 is ~35% of
  events). Fixed by resolving the timestamp first, classifying second, in that
  order, in one place (`int_events_deduped.sql`).

## 5. Data Contract / Schema in Scope
- Source: `novalake.bronze.raw_events` — full envelope + wide `payload` struct,
  unchanged from `v0.1`.
- Targets (5 new models, all `novalake.silver`):
  - `int_events_deduped` — 1 row per deduped `event_id`, **all event types**,
    envelope drift resolved (`resolved_event_timestamp`,
    `event_timestamp_quality`, `resolved_source_system/region/host`); `payload`
    passed through untouched.
  - `int_transactions` — 1 row per deduped `event_id`, `transaction.*` only,
    payload drift resolved (`customer_id_resolved`, `amount_minor_resolved`,
    `currency_clean`, `country_clean`, `risk_score`/`risk_flagged`/
    `risk_reasons`/`risk_malformed`); `line_items` still an array.
  - `int_transactions_clean` / `int_transactions_dlq` — same grain and columns as
    `int_transactions`, split by `event_timestamp_quality`.
  - `int_transaction_line_items` — 1 row per (transaction, line item), or 1
    null-item row for transactions with zero or missing line items
    (`LATERAL VIEW OUTER posexplode`).
- Schema-evolution policy: not addressed yet — single fixed generator schema for
  now; revisit if/when Bronze's inferred schema changes.
- Keys / grain / uniqueness: `event_id` unique in `int_events_deduped` and
  `int_transactions` (tested); `int_transaction_line_items.event_id` is
  many-to-one back to `int_transactions_clean.event_id` (tested via
  `relationships`).

## 6. Step-by-Step Implementation
- **Step 6.1 — `int_events_deduped`**
  - *Objective:* dedupe by `event_id` (max `ingested_at` wins) and resolve
    envelope-level drift, generically across all event types.
  - *Concept:* struct-vs-scalar reshaping (`source`/`source_system`),
    type-equivalent collapse (`event_timestamp` epoch-millis vs ISO).
  - *Task:* `row_number()` window dedup; `case`-branch timestamp/source
    resolution keyed on `schema_version`; exact-literal DLQ sentinel
    classification against the *resolved* timestamp.
  - *Model reference:* `src/dbt/models/intermediate/int_events_deduped.sql`
  - *Expected output:* 1 row per `event_id` across all event types (all 10),
    `event_timestamp_quality ∈ {ok, null, epoch_zero, far_future}`.
  - *Validation check:* `unique`+`not_null` on `event_id`,
    `accepted_values` on `event_timestamp_quality` — **all pass**.
- **Step 6.2 — `int_transactions`**
  - *Objective:* resolve `transaction.*`-specific payload drift.
  - *Concept:* key renaming (`customer_id`/`cust_id`), type-equivalent collapse
    (`amount_minor` as string), unit drift (`amount` major vs `amount_minor`
    minor units), value dirtiness (`currency`, `country`), struct collapse
    (`risk` recovered via `from_json` + regex fallback).
  - *Task:* `coalesce`, `try_cast`, `case`-branched unit conversion,
    `upper(trim(...))` + alias mapping, `from_json`/`regexp_extract` with a
    `risk_malformed` flag.
  - *Model reference:* `src/dbt/models/intermediate/int_transactions.sql`
  - *Expected output:* 1 row per deduped `transaction.*` event, all payload drift
    resolved, `line_items` still an array.
  - *Validation check:* `unique`+`not_null` on `event_id`, `not_null` on
    `customer_id_resolved`/`amount_minor_resolved`/`risk_score`,
    `accepted_values` (`warn`) on `currency_clean` — **14 PASS, 1 WARN** (the one
    intentional `"US$"` invalid-currency warning — expected, not a defect).
    Actual row count: **3,192** (Bronze `transaction.*` = 3,234; dedup removed 42
    replay duplicates, consistent with the dataset's ~1.5% replay rate).
- **Step 6.3 — `int_transactions_clean` / `int_transactions_dlq`**
  - *Objective:* split on `event_timestamp_quality` — quarantine bad timestamps,
    keep everything else.
  - *Concept:* DLQ / quarantine handling — deliberately narrow (timestamp only;
    malformed `risk` is a different, already-decided problem — see §8).
  - *Task:* two one-line `WHERE` filters over `int_transactions`, not two
    independent re-derivations of the drift logic.
  - *Model reference:* `int_transactions_clean.sql`, `int_transactions_dlq.sql`
  - *Expected output:* exhaustive, exclusive split of `int_transactions`.
  - *Validation check:* `not_null` on `resolved_event_timestamp` in the clean
    model — **pass**. Actual counts: clean = **3,042**, DLQ = **150**
    (3,042 + 150 = 3,192 exactly — confirms the split is exhaustive and
    exclusive). DLQ breakdown: `null`=69, `epoch_zero`=55, `far_future`=26.
- **Step 6.4 — `int_transaction_line_items`**
  - *Objective:* flatten `line_items` without silently dropping transactions that
    have zero or missing items.
  - *Concept:* array flattening, the `explode` vs `explode_outer` decision.
  - *Task:* `LATERAL VIEW OUTER posexplode(line_items)` over
    `int_transactions_clean` only (DLQ rows stay unexploded).
  - *Model reference:* `int_transaction_line_items.sql`
  - *Expected output:* ~1.95 rows per clean transaction (accounting for
    genuinely-zero-item and missing-item transactions each contributing exactly
    one null-item row).
  - *Validation check:* `not_null`+`relationships` on `event_id` back to
    `int_transactions_clean` — **pass**. Actual row count: **5,934**
    (5,934 / 3,042 ≈ 1.951 rows/transaction, matching the reasoned expectation).

## 7. Operational Considerations
- Idempotency: all 5 models are views — recompute from Bronze on every run, no
  incremental state to reconcile. Bronze itself is still a full-overwrite batch
  load (`v0.1`'s known follow-up, unchanged here).
- Incremental vs. full refresh: not addressed — views, not incremental
  materializations; revisit once `v0.5` introduces incremental Bronze loading.
- Performance: no partitioning/clustering — dataset is ~7K rows, not a real cost
  concern yet; revisit if/when it becomes one.
- Failure & retry: dbt view models fail loudly on compile error, same as
  `stg_raw_events`. A real DAB job run inherits the existing job's
  retry/notification config from `resources/dbt_job.yml` (unchanged from `v0.1`).

## 8. Data Quality & Governance
- Expectations applied (`src/dbt/models/intermediate/_intermediate.yml`):
  uniqueness + not-null on primary keys, `accepted_values` (error-severity on
  enums that must never drift, `warn`-severity on `currency_clean` since `"US$"`
  is a known, intentional invalid value that should surface rather than fail the
  job), and a `relationships` test tying line items back to their transaction.
- Quarantine/reject handling: **narrow and deliberate.** `int_transactions_dlq`
  quarantines only the timestamp problem (null / epoch-zero / far-future).
  Malformed `risk` (~3% of rows, collapsed to a string like `"score=0.734"`) is
  explicitly **not** quarantined — it's best-effort recovered instead (the score
  survives via regex extraction; `flagged`/`reasons` are genuinely unrecoverable
  from the string form and stay null) and flagged via `risk_malformed` for
  downstream consumers to filter on if they need to. Two different problems, two
  different decided handlings — not conflated.
- Lineage & catalog tags: none applied yet — dbt's own `ref()` dependency graph is
  the lineage source of truth for now.
- Ownership & access: unchanged from `v0.1` (same `DEFAULT` CLI profile, same
  `novalake` catalog).

## 9. Validation & Acceptance Criteria
- [x] `int_transactions` row count reconciles: 3,192 (Bronze `transaction.*` =
      3,234, minus 42 replay duplicates removed by dedup)
- [x] `int_transactions_clean` (3,042) + `int_transactions_dlq` (150) =
      `int_transactions` (3,192) exactly — split confirmed exhaustive and exclusive
- [x] `int_transaction_line_items` row count (5,934) matches the
      `explode_outer` expectation (~1.95 rows/transaction)
- [x] `risk_malformed` flags 99 rows (~3.1% of 3,192), consistent with the
      generator's ~3% malformed-risk rate
- [x] All dbt schema tests green: 14 PASS, 1 WARN (the one intentional `"US$"`
      warning)
- [x] Real DAB job run confirms the same models compile/run on serverless —
      `TERMINATED SUCCESS` (`bronze_ingest` wrote 7,105 rows, `dbt_silver_gold`
      exited clean, confirming all 15 schema tests passed there too); job-written
      table counts (3,192 / 3,042 / 150 / 5,934) match the local run exactly
- [ ] Sign-off: **not given** — this module isn't complete (7 event types +
      multiline file remain)

## 10. Key Takeaways
- Envelope-level drift (dedup, timestamp, source) generalizes cleanly across all
  10 event types; payload-level drift does not, and building it generically
  before it's actually needed would have been premature.
- Bronze's "whole column collapses to one type" behavior, first seen with `risk`
  in `v0.1`, recurs with any dual-typed JSON key — worth checking for on every new
  field touched, not just the ones already known to be dirty.
- DLQ classification must run on the resolved/unified value, not the raw
  pre-cast column, or it silently misses whichever encoding doesn't match the
  sentinel's literal representation.
- A malformed value and a missing value are different problems needing different
  handling even when they look superficially similar — malformed `risk` is
  recovered and flagged; DLQ'd timestamps are quarantined outright.

## 11. Knowledge Check
- **Q1: Why build `int_events_deduped` generically instead of scoping it to
  `transaction.*`?**
  Because `event_id`/`ingested_at` dedup and `event_timestamp`/`source` drift are
  identical-shape problems across all 10 event types — nothing about the fix is
  transaction-specific. Scoping it narrowly now would mean re-deriving the exact
  same logic 7 more times as the remaining event types get their own slices.
- **Q2: Why does a legitimately-zero-line-items transaction get the same
  `explode_outer` treatment as a missing-line-items one?**
  Because both need the parent transaction row preserved, even though the
  *reason* differs (one is a real business fact, the other a data gap). A plain
  inner `explode` would silently drop the parent row in both cases — ~18-19% of
  clean transactions vanishing from the line-items model with no trace.
- **Q3: Why does malformed `risk` stay in the main model instead of going to the
  DLQ?**
  Because it's a different, already-decided problem from the timestamp defects
  the DLQ exists for. The score is genuinely recoverable via regex even when the
  struct collapsed to a string — quarantining a row that's 2/3 recoverable would
  throw away real, usable data for no reason.

## 12. References
- Internal: `docs/01-bronze.md` (the 5-problem-category framing this module
  works through), `docs/_skeleton.md`, `docs/plan.md` (the "one thin vertical
  slice first" precedent this module's scoping follows),
  `data/dictionaries/dataset_guide.md`, `data/generators/generate_events.py`
  (ground truth for every drift/dirty-value rule implemented here)
- Databricks / Spark SQL reference: `from_json`, `LATERAL VIEW` / `posexplode`,
  `timestamp_millis`, `try_cast`, `regexp_extract`

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-20 | Module created. `transaction.*` slice landed: dedupe, envelope + payload drift-fix, DLQ split, line-items explode. Plan reviewed by Opus before and after implementation. Other 7 event types and the multiline file explicitly deferred — module not complete, no `v0.2` tag yet. | Chirag + Claude |
