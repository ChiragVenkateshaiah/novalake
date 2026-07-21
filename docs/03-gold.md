# Module 3 · Gold — Business Metrics & Aggregates

`Status:` Validated  ·  `Owner:` Chirag  ·  `Last updated:` v0.3  ·  `Est. time:` ~1 day

Conformed dimensions, unified fact tables, and business-metric rollups on top
of Silver's two parallel pipelines (NDJSON and multiline). 20 Gold models (3
dimensions, 8 facts, 9 metrics), all passing tests, verified locally and via
hand-checked reconciliation against Silver. Design reviewed by Opus before
implementation — see the Changelog.

## 1. Learning Objectives
- [x] Can explain when two independently-generated sources' identifiers are
      genuinely conformable (shared `customer_id`/`merchant_id` pools,
      verified against both generators) versus when their *shapes* stay
      separate even though the *identities* unify
- [x] Can build a defensively-sparse conformed dimension — one that must
      cover every id seen in any fact, not just ids with rich source
      attributes — and make that sparsity an explicit, tested property
      (`has_multiline_profile`) rather than an implicit gap
- [x] Can recognize when a `UNION ALL` across two sources would silently
      misalign or fail (mismatched struct shape, e.g. `payment_method`) and
      flatten to shared scalars first instead of forcing a whole-struct union
- [x] Can recognize when NOT to build a single blended metric across sources
      whose underlying concepts are genuinely non-equivalent (fx-normalized
      totals; support-ticket resolution time vs. SLA breach) and report two
      separate, clearly-labeled numbers instead
- [x] Can distinguish a real foreign key from a coincidentally-similar field
      (`original_transaction_id`/`related_transaction_id` are random UUIDs,
      never real FKs) and choose an aggregate-ratio metric over a join-based
      one when no real relationship exists to join on

## 2. Prerequisites
- Completed modules: `v0.2` Silver (81 dbt models, both sources' `_clean`
  triples and cross-page dimensions)
- Tables/assets that must already exist: every `_clean` model under
  `models/intermediate/` for both sources, `int_multiline_customers`,
  `int_multiline_merchants`, `int_multiline_fx_rates`,
  `int_multiline_transactions_fx_applied`
- Compute: same as Silver — `dbt-databricks` locally against "Serverless
  Starter Warehouse"; DAB `dbt_task` picks up `models/gold/**` automatically
  (bare `dbt run`/`dbt test`, no `--select` scoping — confirmed, no DAB
  change was needed for this module)

## 3. Where This Fits
- One-line: consumes both Silver pipelines' `_clean` models, produces
  conformed dimensions, unified per-event-family facts, and business-metric
  rollups
- Inputs → this module → Outputs: Silver `_clean` models (both sources) →
  `models/gold/` (dims + facts) → `models/gold/metrics/` (rollups) → future
  `v0.4` Serving (Genie space, dashboards)
- Two atomic layers, one aggregated layer: `models/gold/` holds `dim_*`/`fct_*`
  (reusable building blocks, mirrors Silver's `intermediate/` posture);
  `models/gold/metrics/` holds pre-aggregated, opinionated rollups (a
  different kind of model, worth its own declared folder — same reasoning
  that already separates `staging`/`intermediate`)

## 4. Concepts & Background
- **Shared identity pools, separate payload shapes.** `customer_id`
  (`cust_10000-19999`) and `merchant_id` (`mer_1000-1099`) are drawn from the
  *same* ranges by both generators — real, verified conformable identity —
  even though envelope/payload shapes stay deliberately unreconciled at
  Silver. Gold is where that identity conformance actually gets used
  (`dim_customers`, `dim_merchants`), one layer above where shape unification
  was rejected.
- **Defensively-sparse conformed dimensions.** `int_multiline_customers`
  samples only 40-70 customers/page out of the full pool — most
  `dim_customers` rows have no multiline profile. Built anyway, with
  `has_multiline_profile` making the sparsity an explicit, queryable, tested
  property (296 of 6,296 rows populated) instead of a silent gap a consumer
  might assume is complete. `dim_merchants` uses the identical defensive
  pattern even though this dataset happens to make it fully populated (100 of
  100) — that completeness is a property of *this* dataset, not something to
  assume structurally.
- **Struct-shape UNION hazards.** Multiline's `payment_method` carries a
  `network_tokens` field NDJSON's doesn't — a whole-struct `UNION ALL` would
  misalign or fail. Every fact flattens to shared scalars before unioning,
  never passes a whole struct through.
- **Not forcing false equivalence across sources, twice.** (1) fx: only
  multiline has fx rate data (random-per-page, no real-world grounding) —
  facts keep native currency for both sources; a USD total is computed and
  labeled multiline-only, never fabricated for NDJSON.
  (2) support-ticket performance: NDJSON has real elapsed
  `resolution_minutes`; multiline only has an SLA target/breach flag — no
  conversion exists between them, so two separate metrics are reported
  (`metric_support_resolution_time`, `metric_support_sla_breach_rate_multiline`)
  rather than one blended number. Both decisions made explicitly with the
  project owner, not silently.
- **Degenerate, not foreign, keys.** `refund.original_transaction_id` and
  `support_ticket.related_transaction_id` are independently random UUIDs in
  both generators — never real FKs into any transaction's `event_id`. Kept as
  informational attributes, never `relationships`-tested, never joined on for
  a metric (`metric_refund_rate` is an aggregate ratio at `(event_date,
  source)` grain instead).
- **Money isn't uniformly minor-unit.** Only `transaction.*` has the Silver-
  resolved v1/v2 major-float vs. minor-int drift. `refund.amount` and
  `payout.gross_amount` are plain major-unit floats in both schema versions —
  confirmed against both generators, not assumed from `transaction.*`'s
  pattern.

## 5. Data Contract / Schema in Scope
- Sources: every relevant `_clean`/`_fx_applied` model in `novalake.silver`
  (both NDJSON and multiline pipelines).
- 20 Gold models in `novalake.gold`: `dim_date` (166 rows), `dim_customers`
  (6,296 rows, 296 with a multiline profile), `dim_merchants` (100 rows, all
  with a multiline profile); 8 facts — `fct_transactions` (4,730),
  `fct_refunds` (619), `fct_payouts` (529), `fct_support_tickets` (1,255),
  `fct_reviews` (1,034), `fct_risk_alerts` (515), `fct_auth_sessions` (1,296),
  `fct_kyc_verifications` (511); 9 metric rollups under
  `models/gold/metrics/`.
- Grain/keys: `date_day` unique in `dim_date`; `customer_id`/`merchant_id`
  unique in their dimensions; every fact's surrogate key
  (`concat(source, '_', event_id)`) unique; every fact row count equals the
  exact sum of its two source `_clean` model row counts (verified, not
  assumed).
- Schema-evolution policy: not addressed — same as Silver, fixed generator
  schema for both sources; revisit if/when either Bronze schema changes.

## 6. Step-by-Step Implementation
Delivered as 4 increments on `feat/v0.3-gold`, plan reviewed by Opus before
implementation (two corrections made: a factual error about `v0.2`'s tag
status, and a false verification assertion about `fx_rate_quote_per_usd`'s
nullability — both caught before code was written, not after a failing test).

- **Increment 1 — Conformed dimensions.** `dim_date` (calendar spine,
  `explode(sequence(...))`), `dim_customers`/`dim_merchants` (union of every
  `_clean` model carrying that FK, `LEFT JOIN`ed to multiline's cross-page
  reference dimensions). Verified: `dim_date` = exactly 166 rows;
  `dim_customers.has_multiline_profile` true for 296/6,296 (a real, predicted
  sparse-dimension assertion, not just a row count); `dim_merchants` fully
  populated (100/100).
- **Increment 2 — `fct_transactions`.** The most structurally complex union:
  `payment_method`/`merchant` struct flattening, NDJSON's ~2%-nullable inline
  merchant struct reached via `merchant.merchant_id`, native-vs-USD amount
  split. Verified: row count = `int_transactions_clean` (3,042) +
  `int_multiline_transactions_fx_applied` (1,688) = 4,730 exactly;
  `amount_minor_usd`/`fx_rate_quote_per_usd` both NULL for every `ndjson`
  row; `amount_minor_usd` populated for every `multiline` row, but
  `fx_rate_quote_per_usd` correctly NULL for the 276 USD/`"US$"` multiline
  rows (the fx table's own base currency never gets a rate row) — the exact
  correction the Opus review caught before this was written as a passing
  test.
- **Increment 3 — Remaining 7 facts.** `fct_refunds, fct_payouts,
  fct_support_tickets, fct_reviews, fct_risk_alerts, fct_auth_sessions,
  fct_kyc_verifications`. Every fact's row count verified exact against its
  two source `_clean` models' summed count. `fct_refunds.reason` verified to
  carry the full 5-value union (multiline never emits `item_not_received`,
  confirmed not a defect). `fct_support_tickets` verified: `sla_*` columns
  NULL for every `ndjson` row, `resolved`/`resolution_minutes` NULL for every
  `multiline` row — the two metric-source column pairs never overlap.
- **Increment 4 — 9 metric models + this doc.** `metric_transaction_volume`
  (native currency, grouped by currency), `metric_transaction_volume_usd_multiline`
  (multiline-only USD total), `metric_approval_decline_rate`,
  `metric_refund_rate` (aggregate ratio, not a join),
  `metric_fraud_signals` (two independent measures, deliberate `count(*)`
  denominator for the `risk_malformed` NULLs), `metric_support_resolution_time`
  (ndjson-only) / `metric_support_sla_breach_rate_multiline` (multiline-only,
  the two-metric split decided in Increment 0's planning), `metric_review_ratings_by_merchant`
  (rating-based only, no text sentiment), `metric_payout_latency`. Every
  metric family hand-verified against a raw query (review avg-rating match,
  approval+decline rates summing to exactly 1.0, transaction/refund/fraud
  totals reconciling exactly against fact-table counts).

## 7. Operational Considerations
- Idempotency: all 20 models are views — recompute from Silver on every run,
  no incremental state, same as Silver. Incremental modeling deferred to
  `v0.5`, unchanged decision.
- Performance: no partitioning/clustering — data volumes stay small (largest
  fact, `fct_transactions`, is 4,730 rows); not a real cost concern yet.
- Failure & retry: same as Silver — dbt view models fail loudly on compile
  error; the real DAB job's `dbt_silver_gold` task inherits existing
  retry/notification config, no job-definition change needed for Gold.

## 8. Data Quality & Governance
- Expectations applied (`_gold.yml`/`_gold_metrics.yml`): `unique`+`not_null`
  on every dimension key and fact surrogate key; `relationships` from every
  fact's `event_date`/`customer_id`/`merchant_id` back to its dimension;
  `accepted_values` (warn-severity, same precedent as Silver) on every
  `currency_clean`; `accepted_values` (error-severity) on closed enums
  identical across sources, with `fct_refunds.reason` explicitly using the
  5-value union rather than either source's own narrower list.
- Degenerate keys never `relationships`-tested: `original_transaction_id`,
  `related_transaction_id` — both confirmed random UUIDs in the generators,
  not real FKs, kept informational only.
- Lineage & catalog tags: none applied yet — dbt's own `ref()` graph remains
  the lineage source of truth, same as Silver.
- Ownership & access: unchanged from `v0.1`/`v0.2` — same `DEFAULT` CLI
  profile, same `novalake` catalog.

## 9. Validation & Acceptance Criteria
- [x] All 20 new Gold models build clean (`dbt run`), full project (101
      models) builds clean together
- [x] Full project test suite: 295/302 pass, 7 WARN (all the same intentional
      `"US$"`-currency case — 4 pre-existing from Silver + 3 new from Gold's
      `fct_transactions`/`fct_refunds`/`fct_payouts`), 0 ERROR
- [x] Every fact's row count verified exact against the sum of its two
      source `_clean` model row counts (not just "tests passed")
- [x] `fct_transactions`'s fx-nullability behavior hand-verified precisely
      (native amounts NULL-USD-fields for ndjson; multiline's
      `fx_rate_quote_per_usd` correctly NULL only for USD/`"US$"` rows, not
      all rows — the exact assertion the Opus review corrected before
      implementation)
- [x] `dim_customers`/`dim_merchants` sparsity hand-verified against
      predicted pattern (296/6,296 vs. 100/100)
- [x] Every metric family hand-verified against a raw query: review
      avg-rating exact match, approval+decline rates summing to 1.0 across
      every row, transaction/refund/fraud-signal totals reconciling exactly
      to their source fact tables
- [x] Real DAB job run: `TERMINATED SUCCESS` (`bronze_ingest` 7,105 rows,
      `bronze_ingest_multiline` 9 rows in parallel, `dbt_silver_gold` — now
      including all 20 Gold models). Job-written Gold table counts match
      local runs exactly (spot-checked: `dim_customers`=6,296,
      `dim_merchants`=100, `fct_transactions`=4,730, `fct_refunds`=619,
      `fct_payouts`=529, `fct_support_tickets`=1,255, `fct_reviews`=1,034,
      `fct_risk_alerts`=515, `fct_auth_sessions`=1,296,
      `fct_kyc_verifications`=511) — confirms `dbt_silver_gold` picks up
      `models/gold/**` automatically with no job-definition change, as
      predicted in Step 1 of the design plan
- [x] Sign-off: **given** — module Definition of Done met per
      `CONTRIBUTING.md`

## 10. Key Takeaways
- Two independently-generated sources can share real, verifiable identity
  (`customer_id`/`merchant_id` pools) even when their payload *shapes* stay
  deliberately unreconciled — conformance is a property to verify per-field,
  not assume wholesale from "these describe the same business."
- A conformed dimension that will be genuinely sparse should make that
  sparsity an explicit, tested column, not an implicit gap a consumer has to
  discover by noticing a lot of NULLs.
- The same "don't force false equivalence" principle that shaped Silver's
  two-pipeline design recurs one layer up, at the metric level: fx
  normalization and support-ticket performance both needed two honestly-
  labeled numbers instead of one fabricated blend.
- A plan reviewed by a second model before implementation catches concrete,
  falsifiable errors (a stale tagging claim, an incorrect nullability
  assertion) — the same value Silver's own Opus reviews demonstrated,
  confirmed again here on a materially different kind of model (aggregation,
  not transformation).

## 11. Knowledge Check
- **Q1: Why does `dim_customers` need a `has_multiline_profile` flag but
  `dim_merchants` — built with the identical pattern — ends up not needing
  one in practice?**
  `int_multiline_customers` only samples 40-70 customers/page out of the
  full pool, so most `dim_customers` rows never get a multiline profile row.
  `int_multiline_merchants` samples ~60% of the full 100-merchant range *per
  page*, and across all 9 pages already covers the entire pool — so
  `dim_merchants` happens to be fully populated in this dataset. Both are
  built with the same defensive `LEFT JOIN`, because that completeness is a
  property of this specific dataset's sampling, not something the model
  should assume structurally.
- **Q2: Why is `metric_refund_rate` computed as two independently-aggregated
  CTEs joined on `(event_date, source)`, instead of joining `fct_refunds` to
  `fct_transactions` on `original_transaction_id`?**
  `original_transaction_id` is an independently-generated random UUID in
  both generators — it was never drawn from a real transaction's `event_id`.
  A join on it would silently produce zero matches (or worse, spurious ones
  if IDs ever collided), not a meaningful refund-to-transaction link. The
  aggregate-ratio approach is the only correct one given what the data
  actually contains.
- **Q3: Why does `fct_transactions` NOT have a `not_null` test on
  `fx_rate_quote_per_usd` for multiline rows, even though `amount_minor_usd`
  does?**
  `fx_rates_for_page()` never emits a rate row for USD — it's the fx table's
  own base currency. Every USD (and un-cleanable `"US$"`) multiline
  transaction correctly has a NULL `fx_rate_quote_per_usd` after the `LEFT
  JOIN`, while `amount_minor_usd` still resolves via `coalesce(rate, 1.0)`.
  A blanket `not_null` on the rate column would be testing for behavior the
  model is deliberately not supposed to have.
- **Q4: Why are `metric_support_resolution_time` and
  `metric_support_sla_breach_rate_multiline` two separate models instead of
  one `metric_support_performance` spanning both sources?**
  `resolution_minutes` (real elapsed time) and `sla_breached` (a target/
  breach flag) measure genuinely different concepts with no valid conversion
  between them — NDJSON tickets don't have an SLA target at all, and
  multiline tickets don't record real elapsed resolution time. Blending them
  into one metric would require inventing a relationship the data doesn't
  support.

## 12. References
- Internal: `docs/02-silver.md` (the Silver models and design precedents this
  module builds on), `docs/checkpoint.md` (the "no later-phase tooling
  early" principle behind deferring text-sentiment scoring),
  `data/generators/generate_events.py`, `data/generators/generate_multiline.py`
  (ground truth for every FK/enum/shared-pool claim in this module, verified
  directly, not assumed from field-name similarity)
- Databricks / Spark SQL reference: `sequence`, `explode`, `datediff`,
  `percentile_approx`, `FILTER (WHERE ...)` aggregate clauses, `FULL OUTER
  JOIN`

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-21 | Module created. Plan designed, Opus-reviewed (2 corrections made before implementation), delivered as 4 increments: conformed dimensions (1), `fct_transactions` (2), remaining 7 facts (3), 9 metric models + this doc (4). Module Definition of Done met — see `CONTRIBUTING.md`. | Chirag + Claude |
