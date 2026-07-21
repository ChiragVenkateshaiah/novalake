# Module 4 · Serving Layer

`Status:` Draft  ·  `Owner:` Chirag  ·  `Last updated:` v0.4 (in progress)  ·  `Est. time:` ___

## 1. Learning Objectives
- [ ] Can design a Genie space's table scope and instructions so natural-language
      answers respect the same non-equivalence guardrails Gold's modeling
      already earned (fx-normalized vs. native currency, resolution-time vs.
      SLA-breach, non-FK ratio metrics)
- [ ] Can recognize when a guardrail needs schema-level curation (excluding a
      column/table from the Genie space) rather than prose instructions, for
      cases where the schema itself invites the wrong query (e.g. a
      plausible-looking non-FK join)
- [ ] Can distinguish "average of a pre-computed rate" from "recomputed rate
      from underlying counts" and know which one a cross-grain rollup
      question actually requires

## 2. Prerequisites
- Completed modules: `v0.3` Gold (3 conformed dimensions, 8 fact tables, 9
  metric rollups in `novalake.gold`, tagged `v0.3` — see `docs/03-gold.md`)
- Tables / assets that must already exist: all `novalake.gold.dim_*`,
  `novalake.gold.fct_*`, and `novalake.gold.metric_*` models
- Compute / cluster config: Serverless SQL warehouse ("Serverless Starter
  Warehouse", same as dbt) for both the Genie space and the dashboard

## 3. Where This Fits (Architecture Context)
- One-line: consumes Gold's dims/facts/metrics directly (no new transform
  layer) and exposes them as a natural-language Genie space and an AI/BI
  dashboard
- Reference diagram: `README.md` → Architecture (mermaid), `docs/architecture.md`
- Inputs → this module → Outputs: `novalake.gold.*` (20 models, `v0.3`) →
  Serving (Genie space config + Lakeview dashboard spec) → business users /
  the eventual `v0.6` GenAI layer

## 4. Concepts & Background
- Concept 1: ___
- Concept 2: ___
- **Guardrails carried forward from Gold, plus one new to this layer**
  (reviewed by Opus before implementation — see Changelog). These are the
  things a NL query or a dashboard tile can silently get wrong even though
  Gold itself is correct:
  1. Never blend fx-normalized USD totals (`multiline`-only) with native-
     currency totals (both sources) into one number.
  2. Never blend support-ticket performance across sources: `ndjson`'s real
     `resolution_minutes` and `multiline`'s `sla_breached` target/breach flag
     measure different things — report as two separate metrics, always.
  3. Never join on `refund.original_transaction_id` or
     `support.related_transaction_id` — both are random UUIDs, not real FKs,
     in both generators. Ratio metrics at `(event_date, source)` grain only.
  4. `dim_customers.has_multiline_profile` sparsity (296/6,296) is deliberate
     dataset design, not a data-quality gap — don't flag or "fix" it.
  5. **(New)** Every `metric_*` rate column (`approval_rate`, `decline_rate`,
     `refund_rate`, `sla_breach_rate`, `verified_purchase_rate`, …) is
     pre-computed at a fine grain (`event_date`, `source`, sometimes
     `priority`). A question spanning a coarser grain (a quarter, all
     sources) must recompute the rate from the underlying counts each metric
     already exposes (`sum(completed_count) / sum(completed_count +
     failed_count)`, etc.) — never `AVG()` the rate column itself, which is
     an unweighted mean and silently wrong (Simpson's-paradox trap).
- Also worth naming explicitly (not a guardrail violation risk, but a real
  shape of the data a consumer needs to know): `fct_payouts` has no
  `customer_id` — never attribute a payout to a customer; `fct_transactions
  .merchant_id` is ~2% null on `ndjson` — merchant-grouped rollups silently
  drop those rows, not an error.
- Common pitfalls / gotchas to watch for: carrying forward `v0.3`'s
  non-equivalence decisions (see `docs/03-gold.md` §4) into Genie's
  instructions and the dashboard's tile layout, not re-blending what Gold
  deliberately kept separate — and recognizing when prose instructions are
  enough vs. when the schema itself (a column name, a table's presence in
  scope) needs to be curated away instead, because a capable enough
  text-to-SQL model will find the plausible-looking wrong join if it's
  available to find.

## 5. Data Contract / Schema in Scope
- Source schema (expected): `novalake.gold.dim_date`, `dim_customers`,
  `dim_merchants`; `fct_transactions`, `fct_refunds`, `fct_payouts`,
  `fct_support_tickets`, `fct_reviews`, `fct_risk_alerts`,
  `fct_auth_sessions`, `fct_kyc_verifications`; 9 `metric_*` rollups under
  `models/gold/metrics/` — no new dbt models planned for this phase
- Target schema (produced): a shared question→SQL catalog (the reviewed
  unit), a Genie space definition drafted over a *curated* subset of Gold
  (table scope + instructions + sample questions — `original_transaction_id`
  and `related_transaction_id` excluded from scope, not just instructed
  against), and a dashboard declared as `resources/*.yml` pointing at a
  generated `.lvdash.json` (the JSON itself isn't the reviewed artifact —
  its dataset SQL, pulled from the shared catalog, is). All drafted as
  reviewable repo artifacts, applied to the workspace by hand — see
  `docs/checkpoint.md` (phases `v0.0`–`v0.4` stay hands-on, no agent
  workspace-write access)
- Schema-evolution policy: not applicable — Serving reads Gold as-is
- Keys / grain / uniqueness: not applicable at this layer — see `docs/03-gold.md`
  §5 for Gold's own grain/key contract

## 6. Step-by-Step Implementation
- **Step 6.1 — Shared question→SQL catalog** ✅ drafted, Opus-reviewed
  - *Objective:* one authored-once mapping of business question → vetted SQL
    against Gold, designed before either consumer, so Genie's sample
    questions and the dashboard's tiles draw from the same source of truth
    instead of being designed independently and drifting apart
  - *Task:* for each of the 8 business domains, write the SQL a correct
    answer requires, honoring all 5 guardrails in §4 (recomputed rates from
    counts, never a cross-source blend, never a non-FK join)
  - *Expected output:* `docs/serving/question_catalog.md` — 8 domains + 1
    cross-domain question, each checked against every guardrail; reviewed by
    Opus, 5 corrections folded in (category-level rate rollup, fan-out-safe
    joins via pre-aggregated CTEs, Auth/KYC queries that actually compute a
    rate, an unverified-assumption flag on KYC's `risk_score`, and a missing
    customer-360 question demonstrating guardrail #4 on the dimension that's
    actually sparse)
  - *Validation check:* every SQL pair runs and its result matches the
    underlying metric/fact model's documented grain — ✅ partially confirmed:
    the 6 certified pairs used in Step 6.2 ran live via the deployed Genie
    space (approval/decline, refund rate, SLA breach rate, fraud signals,
    review ratings by category, auth success rate) and returned correct,
    guardrail-respecting results; the remaining catalog entries (KYC,
    payouts, transactions, customer/merchant 360) not yet run live
- **Step 6.2 — Genie space design** ✅ drafted, deployed, and validated
  - *Objective:* curated table scope + guardrail instructions + sample
    questions pulled from the catalog
  - *Task:* draft space config over Gold with `fct_refunds
    .original_transaction_id` and `fct_support_tickets.related_transaction_id`
    excluded from the table scope entirely (schema-level curation, not just
    prose) — safer than trusting instructions alone to prevent the
    plausible-looking non-FK join; instructions still needed for the
    guardrails curation can't structurally enforce (fx blending, support
    metric blending, rate averaging)
  - *Expected output:* `docs/serving/genie_space.md` — display name/
    description, full table scope with the column-exclusion caveat called
    out explicitly, general instructions encoding all 7 guardrails (the
    original 5 plus the payouts-no-customer_id and merchant_id-nullable
    notes), 6 certified example question/SQL pairs for the highest-risk
    questions, and a 16-question sample list for the Genie UI
  - *Validation check:* sample questions return correctly-separated,
    correctly-computed answers where a naive answer would violate a
    guardrail — ✅ done. Deployed by hand as "NovaLake Gold Analytics" (named
    "Genie Agent" in this workspace's UI). Column exclusion, instructions,
    and all 6 certified pairs configured per the spec. 3 guardrail tests run
    live: (1) "approval rate last quarter" correctly resolved "last quarter"
    to Q2 2026 relative to the actual current date and used the certified
    count-based recomputation; (2) "support ticket performance" correctly
    kept `ndjson` resolution time and `multiline` SLA breach rate as two
    separate answers, and its 47% overall breach figure was the
    count-weighted recomputation, not the naive per-priority average
    (47.7%) — confirms guardrail #5 held, not just #2; (3) "total
    transaction volume in USD this year" correctly labeled the figure as
    multiline-only rather than blending in `ndjson`
- **Step 6.3 — Dashboard design** ✅ drafted
  - *Objective:* one tile set per business domain, each backed by catalog SQL
  - *Task:* the dataset SQL (from the catalog) is the reviewed unit; declare
    the dashboard as a `resources/*.yml` DAB entry pointing at a generated
    `.lvdash.json` (following the `resources/dbt_job.yml` precedent for what's
    hand-reviewed vs. generated) rather than hand-authoring the JSON's
    widget/layout tree directly
  - *Expected output:* `docs/serving/dashboard.md` — 11 datasets (one per
    domain, widget-ready column names/date-trunc added), a 3-page/widget
    layout plan sized per the `databricks-aibi-dashboards` skill's grid and
    cardinality rules, and an illustrative (not-yet-created)
    `resources/dashboard.yml` snippet for later DAB wiring
  - *Validation check:* every tile's underlying query runs and matches the
    metric model's documented grain — pending: the skill's own mandatory
    workflow (`get_table_stats_and_schema` → `execute_sql` on every dataset →
    build JSON → `manage_dashboard`) needs live workspace access this phase
    intentionally doesn't use; run it by hand or in an explicitly-authorized
    future session

## 7. Operational Considerations
- Idempotency / re-run safety: ___
- Incremental vs full refresh: ___
- Performance (partitioning / clustering / file sizing): ___
- Failure & retry behaviour: ___

## 8. Data Quality & Governance
- Expectations / rules applied: ___
- Quarantine / reject handling: ___
- Lineage & catalog tags: ___
- Ownership & access: ___

## 9. Validation & Acceptance Criteria
- [x] Genie space created in workspace, answers respect Gold's non-equivalence
      guardrails — "NovaLake Gold Analytics", deployed by hand 2026-07-21,
      3 guardrail tests passed live (see Step 6.2 above)
- [ ] Dashboard created in workspace, every tile backed by a documented Gold
      model
- [ ] Sign-off: ___

## 10. Key Takeaways
- ___

## 11. Knowledge Check
- Q1: ___

## 12. References
- Internal: `docs/03-gold.md`, `docs/checkpoint.md`, `docs/architecture.md`,
  `docs/serving/question_catalog.md`, `docs/serving/genie_space.md`,
  `docs/serving/dashboard.md`
- Databricks docs / skills used: `databricks-genie` (space config /
  `serialized_space` shape), `databricks-aibi-dashboards` (dataset/widget/
  cardinality rules, mandatory validation workflow), `databricks-bundles`
  (dashboard resource YAML shape)

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-21 | Module scaffolded from `docs/_skeleton.md`; architecture context, prerequisites, and step outline filled in | Chirag + Claude |
| 2026-07-21 | Plan reviewed by Opus before implementation (four corrections made: missing rate-averaging guardrail, all-20-tables Genie scope invites the non-FK join Gold avoided, `.lvdash.json` isn't hand-reviewable the way `dbt_job.yml` is, no shared question→SQL catalog feeding both consumers) — all four folded in above | Chirag + Claude |
| 2026-07-21 | Steps 6.1–6.3 drafted: `docs/serving/question_catalog.md` (Opus-reviewed, 5 corrections), `docs/serving/genie_space.md`, `docs/serving/dashboard.md`. Nothing deployed to the workspace this session, per `docs/checkpoint.md` — §9 acceptance criteria remain pending until you run the deployment/validation steps each spec file calls out | Chirag + Claude |
| 2026-07-21 | Genie space ("NovaLake Gold Analytics") deployed by hand, per `docs/checkpoint.md` (Chirag created it in the workspace UI; Claude guided step by step and reviewed the result, no MCP write calls made). Table scope, column exclusion (`original_transaction_id`, `related_transaction_id`), 7-point instructions, and 6 certified query pairs configured per `docs/serving/genie_space.md`. 3 live guardrail tests passed: source-scoped rate recomputation (guardrail #5), never blending support-ticket metrics across sources (guardrail #2), never blending fx-normalized USD into a native-currency total (guardrail #1). §9's Genie criterion checked off | Chirag + Claude |
