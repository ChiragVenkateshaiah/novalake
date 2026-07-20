# Module 2 · Silver — Conform, Cleanse, Explode

`Status:` Validated  ·  `Owner:` Chirag  ·  `Last updated:` v0.2  ·  `Est. time:` ~1 day

Full scope landed: all 10 event types across both raw sources
(`payments_events.json` and `payments_events_multiline.json`) — dedupe, envelope
and payload drift resolution, DLQ split, array explode (including two-level
nesting), dynamic-key-map reconstruction, cross-page dimension resolution, fx
normalization, and record-count reconciliation. 81 dbt models, 175/179 tests
green (4 intentional `"US$"` warnings), verified locally and via a real DAB job
run on serverless (`TERMINATED SUCCESS`, table counts matching exactly between
local and job runs). Delivered as 8 sequential increments (0-7), each reviewed
by Opus before implementation, verified, and committed independently — see the
Changelog for the full sequence and `docs/plan.md` for the complete design
history (three rounds: the initial `transaction.*` slice plan, its Opus review,
and the remaining-scope plan covering the other 9 event-type/source
combinations, itself revised twice from Opus review before and after
Increment 4's empirical schema discovery).

## 1. Learning Objectives
- [x] Can explain why envelope-level drift resolution (dedup, timestamp, source,
      and — once evidenced across enough event types — key-renamed identifiers)
      is built generically while payload-level fixes stay scoped per event family
- [x] Can name which SQL construct fixes each of the 5 Silver problem categories
      from `docs/01-bronze.md` §8: struct collapse → `from_json`, type-equivalent
      collapse → `try_cast`, key renaming → `coalesce`, structural reshaping →
      version-branched `case`, value dirtiness → macro-wrapped normalization
- [x] Can explain why `LATERAL VIEW OUTER posexplode` is the right choice when an
      array can be *both* genuinely empty *and* separately missing — and why a
      generator's actual cardinality logic, not a blanket rule, decides which
      arrays need it (some don't, and using it there is defensive noise, not safety)
- [x] Can extend the same envelope/payload/DLQ/explode pattern to a second,
      structurally incompatible raw source (the multiline file) without
      unifying its pipeline with the first — recognizing when two sources are
      similar enough to share logic and when forcing a shared abstraction would
      cost more than it saves
- [x] Can recognize a genuine dynamic-key-map ("schema-explosion trap") field,
      distinguish it from a closed-enum field that merely looks similar, and
      reconstruct the former as an actual `MAP` type via `to_json`+`from_json`
      rather than leaving Bronze's inferred struct in place

## 2. Prerequisites
- Completed modules: `v0.0` (setup), `v0.1` (Bronze ingest of
  `novalake.bronze.raw_events`, DAB/dbt wiring, `stg_raw_events` pass-through)
- Tables/assets that must already exist: `novalake.bronze.raw_events` (7,105 rows),
  `novalake.bronze.raw_events_multiline` (9 rows, landed in this module —
  `payments_events_multiline.json`'s Bronze capture was deliberately deferred to
  the start of `v0.2`, per `docs/01-bronze.md`)
- Compute: `dbt-databricks` locally against "Serverless Starter Warehouse"; DAB
  `dbt_task`/two parallel `spark_python_task`s on serverless (unchanged pattern
  from `v0.1`, extended with a second Bronze task — checked against Databricks
  Free Edition's 5-concurrent-task-per-account limit, peaks at 2)

## 3. Where This Fits
- One-line: consumes both Bronze sources' lossless raw envelopes, produces
  conformed, deduped, drift-resolved, DLQ-split, exploded, dimension-resolved
  Silver models for all 10 event types
- Two **parallel, not unified** pipelines, by deliberate design (see §4):
  - NDJSON: `novalake.bronze.raw_events` → `stg_raw_events` → `int_events_deduped`
    (generic: dedup, envelope drift, `customer_id_resolved`) → 8 per-event-type
    `int_<type>` / `_clean` / `_dlq` triples → child explode models
  - Multiline: `novalake.bronze.raw_events_multiline` → `stg_raw_events_multiline`
    → `int_multiline_events` / `int_multiline_partial_failures` (first explode)
    → `int_multiline_events_deduped` (generic, own dedup tie-break) → 8
    per-event-type triples → child explodes (including two-level nesting) →
    `int_multiline_merchants` / `_customers` / `_fx_rates` (cross-page dimensions)
    → `int_multiline_transactions_fx_applied` → `int_multiline_record_count_reconciliation`
- `int_events_deduped` / `int_multiline_events_deduped` are the reusable generic
  layers every event-type model in their respective pipeline builds on.

## 4. Concepts & Background
- **Generic vs. scoped layering, extended.** The `transaction.*` slice
  established dedup/timestamp/source as generic. Building the other 7 NDJSON
  types revealed `customer_id`/`cust_id` key-renaming is shared by 9 of 10 event
  types (only `payout.scheduled` has no customer key) — promoted into the
  generic layer too, with the already-shipped `int_transactions` refactored to
  consume it (Increment 0), verified via a full-row `EXCEPT`-based diff, not
  just row-count/test parity (row counts alone can't catch value-level
  corruption from a refactor — Opus review's central catch on this module).
- **Two sources, two pipelines — not unified.** The multiline envelope has no
  `ingested_at` field (dedup needs a different, arbitrary-but-safe tie-break,
  since its replays are byte-identical copies); payload shapes are already
  incompatible per event type between the two sources (e.g.
  `transaction.completed`'s `amount`/`risk` live under `payload.transaction.*`
  in multiline, flat under `payload.*` in NDJSON — confirmed field-by-field
  against both generators, not assumed from "same event type name"). Forcing a
  shared envelope layer would have bought little while risking the already-shipped
  NDJSON pipeline.
- **Bronze's schema-collapse mechanism recurs a third time.** First `risk`
  (`v0.1`), then `event_timestamp` (this module's first slice), then multiline's
  `payload.transaction.risk` (same collapse, now with an added `signal_matrix
  array<array<double>>` field inside the recovered struct — a construct not
  seen in the NDJSON version). Worth checking on every new dual-typed field.
- **Dynamic-key-map fields: real vs. apparent.** Empirical schema discovery
  (`describe` on the real Bronze-inferred multiline schema, Increment 4) showed
  every dynamic-key map lands as a *bounded*, named-field struct — not the
  unbounded explosion the "schema-explosion trap" framing warns about — because
  every one of this generator's dynamic maps draws from a fixed key universe.
  The principled fix (Opus review, reframing an earlier "pick one to
  demonstrate" draft): reconstruct fields with **open-vocabulary, descriptive**
  keys (`metadata`, `device.sensors`, `line_items[].attributes` — genuinely
  could have unbounded keys in a less-controlled generator) or **lookup-keyed**
  purpose (`balances`, joined against currency codes) as actual
  `MAP<STRING,STRING>` via `to_json`+`from_json`; leave **closed-enum** fields
  (`tax_ids`, `consents`, `checksums`, `currency_catalog`, `reactions` — keys
  drawn from a small fixed vocabulary, legitimately structs) as direct
  struct-field access. Not an arbitrary split — a principle that would extend
  to a real, less-controlled dataset.
- **fx application: rate direction and the missing base-currency row.**
  `fx_rates_for_page()` never emits a `USD` rate row (it's the base currency,
  skipped by the generator's own logic) — an inner join would silently drop or
  null every USD transaction's normalized amount. `LEFT JOIN` +
  `coalesce(rate, 1.0)` is required, not a defensive nicety. Rate semantics
  (`base: USD, quote: X, rate: R` means `1 USD = R units of X`) verified before
  writing the conversion direction — converting quote→USD *divides* by the
  rate, doesn't multiply.
- **Reconciliation grain matters.** `record_counts.events` is computed by the
  generator *after* within-page replay duplicates are appended — reconciling
  against the *deduped* event count (rather than the raw exploded count) would
  have silently mixed the generator's intentional reconciliation delta with an
  unrelated ~1.4% dedup effect. Caught in Opus review before implementation.
- **A join that fans out is a correctness bug, not a style choice.** An early
  draft of the reconciliation model joined unaggregated per-page events and
  per-page failures directly on `page` — every event row paired with every
  failure row on that page, silently inflating both counts. Caught before
  running (not after seeing wrong numbers) by pre-aggregating each side to page
  grain in its own CTE first.

## 5. Data Contract / Schema in Scope
- Sources: `novalake.bronze.raw_events` (7,105 rows, unchanged from `v0.1`),
  `novalake.bronze.raw_events_multiline` (9 rows, landed in this module,
  `src/ingest_multiline.py` — same lossless, zero-transformation principle as
  `v0.1`, deliberately including the dynamic-key-map fields left un-shaped at
  Bronze).
- 81 Silver models across `models/staging/` (2 pass-throughs) and
  `models/intermediate/` (79 models: 2 generic dedup layers, 2 dbt macros
  (`clean_currency`, `clean_country`), 10 event-type `_resolved`/`_clean`/`_dlq`
  triples per source minus `payout` (no customer key) — i.e. 8 triples × 2
  sources = 16 triples worth of resolved/clean models (`int_transactions_dlq`
  is the one canonical example built with its NDJSON payload-level detail;
  every other type/source combination follows the identical `_clean`/`_dlq`
  pattern for symmetry) — plus ~30 child explode models (single- and two-level
  nesting) and the multiline-only cross-page/fx/reconciliation models.
- Grain/keys, by family: `event_id` unique per source's deduped/resolved layer
  (tested); every child explode model's parent key is `relationships`-tested
  back to its `_clean` parent; `merchant_id`/`customer_id` unique in the
  resolved dimension models; `page` unique in the reconciliation model
  (9 rows, one per multiline page).
- Schema-evolution policy: not addressed — fixed generator schema for both
  sources; revisit if/when either Bronze schema changes.

## 6. Step-by-Step Implementation
Delivered as 8 increments, each independently planned (with Opus review),
implemented, verified, and committed on `feat/v0.2-silver` — see the Changelog
for commit-level detail. Summary by increment:

- **Increment 0** — refactored the already-shipped `int_transactions` onto a
  newly generic `customer_id_resolved` (`int_events_deduped`) and two new dbt
  macros (`clean_currency`, `clean_country`), verified via a full-row
  `EXCEPT`-based before/after diff (0 rows either direction), not just
  row-count/test parity.
- **Increment 1** — `auth.session` (new payload-level `device` struct-vs-flat
  reshaping), `review.submitted` (no drift beyond the generic layer),
  `refund.issued` (`clean_currency`). No arrays.
- **Increment 2** — `kyc.verification` (`documents[]`, plain explode — always
  ≥1), `payout.scheduled` (`fees[]`, `explode_outer` — can be 0; no
  `customer_id_resolved`, this type has no customer key), `risk.alert`
  (`signals[]`, plain explode).
- **Increment 3** — `support.ticket`: two independent sibling arrays
  (`tags[]` `explode_outer`, `messages[]` plain explode) plus free text kept
  as-is for the future GenAI layer.
- **Increment 4** — `src/ingest_multiline.py` lands
  `payments_events_multiline.json` into Bronze (9 rows); first-level explode
  (`int_multiline_events`, `int_multiline_partial_failures`); real empirical
  schema discovery confirming the bounded-dynamic-map hypothesis and surfacing
  the `record_counts.customers`/`.merchants` always-null-STRING quirk.
- **Increment 5** — `int_multiline_events_deduped` (own dedup tie-break, no
  `ingested_at`) + `int_multiline_transactions` (payload now one level deeper,
  `payload.transaction.*`, `risk` recovery now includes `signal_matrix`).
- **Increment 6** — the largest increment: all remaining 7 event types in the
  multiline payload shape (several nested one level deeper than NDJSON, e.g.
  `payload.review.*`/`payload.ticket.*`), every array explode including new
  two-level nestings, and the dynamic-key-map `MAP` reconstruction.
- **Increment 7** — cross-page `merchants` (latest-wins by `as_of_page`, a real
  ordering signal) / `customers` (arbitrary tie-break, no real ordering signal
  exists) dimension resolution, `fx_rates` union, fx-normalized transaction
  amounts, `partial_failures` DLQ parsing, `record_counts` reconciliation.

Full field-level detail for the `transaction.*` slice (Increment 0-era) is
preserved below for reference; the remaining increments follow the identical
resolved→clean/dlq→explode pattern per event type/array, verified the same way
each time (`dbt run`+`dbt test`, row-count spot checks against generator-derived
expectations, real query verification of anything non-obvious like fx math or
MAP contents) — not re-enumerated field-by-field here to keep this module
readable; see each model's own file comments for its specific field mapping.

- *Step 6.1 — `int_events_deduped` / `int_multiline_events_deduped`*:
  generic dedup + envelope drift resolution (+ `customer_id_resolved`),
  `unique`+`not_null`+`accepted_values` — **all pass**.
- *Step 6.2 — per-event-type `_resolved` models*: payload drift resolution,
  scoped per type; `unique`+`not_null` on keys, `accepted_values` (`warn`) on
  every `currency_clean` — **175/179 pass, 4 intentional `"US$"` warnings**.
- *Step 6.3 — `_clean`/`_dlq` pairs*: one-line `WHERE` filters, exhaustive and
  exclusive by construction, spot-checked on every type (e.g.
  `3,042 + 150 = 3,192` for `transaction.*`; `1,688 + 88 = 1,776` for
  multiline `transaction.*`).
- *Step 6.4 — child explode models*: `explode` vs `explode_outer` decided
  per-array from the generator's actual cardinality logic (never assumed),
  `relationships`-tested back to each parent `_clean` model.

## 7. Operational Considerations
- Idempotency: all 81 models are views — recompute from Bronze on every run, no
  incremental state. Both Bronze sources are still full-overwrite batch loads
  (`v0.1`'s known follow-up, unchanged here).
- Incremental vs. full refresh: not addressed — views; revisit once `v0.5`
  introduces incremental Bronze loading.
- Performance: no partitioning/clustering — both sources are small (~7K and
  ~4K rows); not a real cost concern yet.
- Failure & retry: dbt view models fail loudly on compile error. The real DAB
  job (`bronze_ingest` + `bronze_ingest_multiline` in parallel → `dbt_silver_gold`)
  inherits existing retry/notification config; peak task concurrency (2) checked
  against Databricks Free Edition's 5-concurrent-task-per-account limit before
  the second Bronze task was added.

## 8. Data Quality & Governance
- Expectations applied (`_intermediate.yml`/`_staging.yml`): uniqueness +
  not-null on primary keys, `accepted_values` (error-severity on enums that
  must never drift, `warn`-severity on every `currency_clean` since `"US$"` is
  a known, intentional invalid value that should surface, not fail the job),
  `relationships` tying every child explode back to its parent.
- Quarantine/reject handling, three distinct mechanisms, not conflated:
  1. **Timestamp DLQ** (`_dlq` models, every event type/source) — narrow and
     deliberate, timestamp-quality only.
  2. **Malformed `risk`** — best-effort recovered (regex-extracted score) and
     flagged (`risk_malformed`), not quarantined — a different, already-decided
     problem from timestamp defects.
  3. **`partial_failures`** (multiline only) — genuinely alien-schema
     dead-letter records, parsed via `from_json` for visibility, kept in their
     own quarantine table, never joined into the clean event pipeline.
- Reconciliation: `int_multiline_record_count_reconciliation` surfaces
  `export_metadata.record_counts`' intentional mismatch against actual
  (pre-dedup) counts — does not "fix" it, there's nothing to fix.
- Lineage & catalog tags: none applied yet — dbt's own `ref()` graph is the
  lineage source of truth for now.
- Ownership & access: unchanged from `v0.1` (same `DEFAULT` CLI profile, same
  `novalake` catalog).

## 9. Validation & Acceptance Criteria
- [x] All 81 dbt models build clean (`dbt run`, both locally and via the real
      DAB job)
- [x] 175/179 dbt tests pass; the 4 WARNs are all the same intentional
      `"US$"`-currency case, once per model family that resolves currency
      (`int_transactions`, `int_refunds`, `int_payouts`, `int_multiline_transactions`)
- [x] Every `_clean`/`_dlq` split confirmed exhaustive and exclusive by direct
      count (spot-checked across every event type/source)
- [x] Real DAB job run: `TERMINATED SUCCESS` — `bronze_ingest` (7,105 rows),
      `bronze_ingest_multiline` (9 rows, in parallel), `dbt_silver_gold` (all
      81 models + 179 tests). Job-written table counts match local runs
      exactly (spot-checked: `int_transactions_clean`=3,042,
      `int_multiline_transactions_clean`=1,688, `int_support_tickets_clean`=788,
      `int_multiline_merchants`=100, `int_multiline_record_count_reconciliation`=9)
- [x] Increment 0's refactor verified value-for-value (full-row `EXCEPT` diff,
      0 rows either direction), not just row-count/test parity
- [x] fx conversion hand-verified against real output (INR: `2893/99.5142≈29`,
      CAD: `69197/86.3267≈802`), USD rows confirmed unchanged
      (`amount_minor_usd = amount_minor_resolved`)
- [x] `int_multiline_fx_rates` row count = 54 exactly (6 non-USD currencies ×
      9 pages), `int_multiline_merchants` = 100 exactly (the full
      `mer_1000`-`mer_1099` id range)
- [x] Sign-off: **given** — module Definition of Done met per
      `CONTRIBUTING.md` (see below)

## 10. Key Takeaways
- Envelope-level drift generalizes cleanly across all event types within a
  source; payload-level drift does not, and building either prematurely (too
  early, or across sources that don't actually share structure) costs more
  than it saves.
- A refactor of already-shipped code needs value-level verification, not just
  row-count or test parity — both can stay identical while the actual values
  silently drift.
- Two data sources describing "the same" business events can need genuinely
  separate pipelines when their structural assumptions (an `ingested_at`
  field, a flat vs. nested payload shape) diverge — recognizing when *not* to
  force a shared abstraction is as much the skill as building one.
- A dynamic-key-map field is only a real "schema-explosion trap" when its keys
  are open-vocabulary or unbounded in principle — empirically verifying a
  field's actual inferred schema (not just its conceptual shape) determines
  whether the MAP-reconstruction fix is needed or whether direct struct access
  is already correct.
- fx/unit-conversion direction and a missing base-currency rate row are the
  kind of silent-wrong-number bugs that don't fail loudly — verify the
  generator's actual semantics and hand-check real converted values, don't
  trust that a join "worked" just because it returned rows.
- A join on a coarser key than the data's real grain (page, not event/failure)
  fans out silently — caught here by reasoning about cardinality before
  running, not by debugging an inflated count after the fact.

## 11. Knowledge Check
- **Q1: Why does `payout.scheduled` never get a `customer_id_resolved` value,
  even though the generic layer computes it for every event type?**
  Because `payout.scheduled`'s payload has no `customer_id`/`cust_id` field at
  all (it's merchant-centric) — `coalesce()` over two always-null inputs
  correctly resolves to `NULL`, not an error. Confirmed against the generator
  before assuming the generic promotion was safe for this type too.
- **Q2: Why are the NDJSON and multiline pipelines kept fully separate instead
  of sharing one generic envelope-resolution layer across both sources?**
  The multiline envelope has no `ingested_at` field (a different dedup
  tie-break is needed), and payload shapes for "the same" event type are
  already incompatible between sources (nesting depth, field names). Unifying
  them would add real complexity and real risk to already-shipped NDJSON logic
  for little benefit, since the two sources don't actually share structure
  below the envelope's top two or three fields.
- **Q3: Why is `metadata` reconstructed as a `MAP`, but `tax_ids` is left as a
  struct, even though both were dynamic-key fields in the source JSON?**
  `metadata`'s keys are open-vocabulary/descriptive (`dyn_metadata()`) — only
  bounded in this dataset because the generator's key pool happens to be
  finite, not because the concept is closed. `tax_ids`'s keys are drawn from a
  fixed 3-entry enum (`vat`/`gst`/`ein`) — a struct is the *correct* model for
  a closed set, not a simplification of a "real" map.
- **Q4: Why does the fx-application model use `LEFT JOIN` +
  `coalesce(rate, 1.0)` instead of a plain `INNER JOIN`?**
  Because the generator never emits a `USD` rate row (it's the fx table's own
  base currency) — an inner join would silently drop or null every USD
  transaction's normalized amount. The `coalesce` treats "no rate needed
  because it's already USD" as rate `1.0`, which is correct, not a fallback
  hack.

## 12. References
- Internal: `docs/01-bronze.md` (the 5-problem-category framing), `docs/plan.md`
  (three rounds of design history — the `transaction.*` slice, its Opus
  review, and the full remaining-scope plan with its own Opus reviews before
  and after Increment 4), `data/dictionaries/dataset_guide.md`,
  `data/dictionaries/dataset_guide_multiline.md`,
  `data/generators/generate_events.py`, `data/generators/generate_multiline.py`
  (ground truth for every drift/dirty-value/cardinality rule implemented here
  — read directly and re-verified multiple times through this module, not
  assumed from the dataset guides' prose summaries)
- Databricks / Spark SQL reference: `from_json`, `to_json`, `LATERAL VIEW` /
  `posexplode`, `timestamp_millis`, `try_cast`, `regexp_extract`, `MAP` types

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-20 | Module created. `transaction.*` slice landed (Increment 0-era, pre-increment-numbering): dedupe, envelope + payload drift-fix, DLQ split, line-items explode. Plan reviewed by Opus before and after implementation. | Chirag + Claude |
| 2026-07-20 | Full remaining scope planned (7 NDJSON event types + multiline file), reviewed by Opus twice (initial design, then post-Increment-4 revision informed by real empirical schema discovery). Delivered as Increments 0-7: generic `customer_id_resolved` + macro refactor (0, value-diff verified); `auth.session`/`review.submitted`/`refund.issued` (1); `kyc.verification`/`payout.scheduled`/`risk.alert` (2); `support.ticket` (3); multiline Bronze landing + first explode + schema discovery (4); multiline dedup + `transaction.*` (5); multiline arrays + dynamic-map MAP reconstruction + remaining 7 types (6); cross-page dimensions + fx + DLQ parsing + reconciliation (7). Module Definition of Done met — see `CONTRIBUTING.md`. | Chirag + Claude |
