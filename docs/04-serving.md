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
- **Step 6.3 — Dashboard design** ✅ drafted and built
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
    metric model's documented grain — ✅ done, built by hand as "NovaLake
    Gold Analytics" (3 pages, all 11 datasets). 2 real bugs found and fixed
    during the build, not caught by the earlier SQL-level review: (1)
    `ds_approval_decline_rollup` filtered on `current_date()`, which fell in
    Q3 2026 — outside the dataset's fixed 2026-01-01–06-15 range — producing
    a `null` KPI; fixed by anchoring to the latest date in `dim_date`
    instead of the wall clock; (2) the Payment Latency chart silently summed
    p50/p90 percentiles across the `schedule_status` dimension (percentiles
    aren't additive across categories, unlike counts); fixed by adding
    `schedule_status` as a Facet. Every other widget's scale was manually
    sanity-checked (rates 0–1, ratings 1–5, no stray negative axes) before
    acceptance. Exported to `src/dashboards/novalake_gold_analytics.lvdash.json`
    and wired into the bundle as `resources/dashboard.yml`
    (`novalake_gold_analytics`, dev-only per `docs/adr/0003`); deployed via
    `databricks bundle deploy` (bound to the existing `dashboard_id`, no
    recreate — required dropping `mode: development`'s auto name-prefix and
    setting `parent_path` explicitly, see Changelog) and published. Live at
    `/sql/dashboardsv3/01f184fceb11160fa8d7982ad7bb345b` — see Changelog,
    2026-07-22

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
- [x] Dashboard created in workspace, every tile backed by a documented Gold
      model — "NovaLake Gold Analytics", built by hand 2026-07-21, 3 pages /
      11 datasets, 2 bugs found and fixed live (see Step 6.3 above); exported,
      wired into the DAB bundle, deployed, and published 2026-07-22
      (`resources/dashboard.yml`, `databricks bundle deploy` adopted the
      existing dashboard in place — `dashboard_id`/`create_time` unchanged)
- [x] Sign-off: Chirag — 2026-07-22

## 10. Key Takeaways
- Guardrails don't transfer to a new consumer for free: the same 5 (now 7)
  rules from Gold had to be re-enforced at the serving layer in two
  different mechanisms depending on whether the risk was structural
  (`original_transaction_id`/`related_transaction_id` excluded from the
  Genie table scope entirely — prose alone won't stop a capable text-to-SQL
  model from finding a plausible-looking wrong join if the column is
  reachable) or semantic (fx blending, cross-source metric blending, rate
  averaging — nothing in the schema signals these are wrong, so only
  instructions can catch them).
- A shared question→SQL catalog authored once, before either consumer
  existed, kept Genie's sample questions and the dashboard's datasets from
  independently reinventing (and potentially drifting apart on) the same
  guardrail logic.
- SQL-level review and actually building the artifact catch different
  classes of bug: Opus's review of the catalog's SQL confirmed every query
  was structurally correct, but 2 real bugs only surfaced once the
  dashboard was built and rendered — a `current_date()` anchoring bug that
  only manifests against a dataset with a fixed historical range, and a
  percentile-summing bug that's a property of the widget's chart config,
  not the underlying SELECT. Spec review and build-time validation are
  complementary, not substitutes for each other.
- The rate-averaging guardrail (#5) is the same Simpson's-paradox trap as
  Gold's own aggregation layer, just recurring one level up at the serving
  layer — guardrails compound through layers of a lakehouse rather than
  being solved once and inherited automatically.
- Wiring an already-built dashboard into a DAB bundle without destroying it
  is harder than the job-resource case: Lakeview dashboards can't rename or
  move in place, so `display_name` and `parent_path` both had to match the
  live object *exactly*, and `mode: development`'s automatic name-prefix
  turned out to be unsuppressable via its own documented override
  (`presets.name_prefix: ""` is silently ignored — a CLI Go zero-value
  quirk, not something `bundle validate` warns about). The safe path was
  binding the existing resource (`bundle deployment bind`) before ever
  deploying, and verifying `dashboard_id`/`create_time` were unchanged
  afterward, rather than trusting the plan output alone.
- Each new workspace-touching capability (export, then wire, then deploy,
  then publish) was raised and approved as its own explicit exception to
  `docs/checkpoint.md`'s hands-on rule, rather than treating one approval as
  blanket cover for the rest — `bundle deploy` in particular is the exact
  action the checkpoint names, and it also refused to run destructively
  without human approval on its own, independent of that project-level rule.

## 11. Knowledge Check
- **Q1: Why does the Genie space exclude `original_transaction_id` and
  `related_transaction_id` from its table scope entirely, instead of just
  instructing Genie not to join on them?**
  Both are random UUIDs in both generators — a plausible-looking join, not
  a real relationship. A prose instruction describes intent, but doesn't
  remove the model's structural ability to find and use the column anyway
  if it's present in scope. Schema-level curation is used specifically for
  guardrails the schema itself invites violating; prose instructions are
  reserved for guardrails curation *can't* structurally enforce (you can't
  remove a column to stop someone from blending two valid, present columns
  the wrong way — fx totals, cross-source support metrics, rate columns —
  so those stay instruction-only).
- **Q2: The live "support ticket performance" guardrail test returned a 47%
  overall breach rate, not the 47.7% you'd get by averaging each priority's
  `sla_breach_rate`. Why do these differ, and which one is correct?**
  47% is `sum(breached_count) / sum(ticket_count)` recomputed across all
  priorities — the correct, count-weighted figure. 47.7% is the unweighted
  mean of four already-computed per-priority rates, which silently
  over-represents low-ticket-volume priorities relative to their true share
  of total tickets. This is guardrail #5's Simpson's-paradox trap, and the
  live test confirmed it held under a real cross-grain question, not just
  in the reviewed SQL.
- **Q3: Why did `bundle deploy` still want to delete and recreate the
  dashboard even after `display_name` was fixed to match the deployed
  dashboard exactly?**
  Two independent mismatches were forcing the recreate, not one: the
  `display_name` mismatch (fixed first), and a `parent_path` mismatch — the
  bundle's default is to place the dashboard under its own managed
  `.bundle/novalake/dev/resources` folder, which differs from where the
  hand-built dashboard actually lives (`/Users/<email>`). Lakeview
  dashboards can't rename *or* move in place, so both fields had to match
  the live object simultaneously before `bundle deploy` would update in
  place instead of recreating.
- **Q4: Why did building the dashboard surface 2 real bugs that Opus's
  SQL-level review of the exact same queries didn't catch?**
  The review validated that each query was structurally correct in
  isolation — right joins, right guardrails, right output shape. Neither
  bug was a SQL-correctness problem: the `current_date()` bug only
  manifests when the query actually runs against a dataset whose data is
  historically bounded (not visible from reading the SQL text), and the
  percentile-summing bug is a property of how the chart widget aggregates
  across a dimension (`schedule_status`) it wasn't split by — a charting
  config issue invisible to a review of the underlying `SELECT`. Spec
  review and build-time validation catch genuinely different failure
  classes.

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
| 2026-07-21 | Dashboard ("NovaLake Gold Analytics") built by hand in the workspace, same guided/no-MCP-writes process. 3 pages, all 11 datasets from `docs/serving/dashboard.md`. 2 real bugs found and fixed live, beyond what the SQL-level review caught: `ds_approval_decline_rollup`'s `current_date()` filter fell outside the dataset's fixed historical range (fixed to anchor on `dim_date`'s latest date); the Payment Latency chart silently summed p50/p90 percentiles across `schedule_status` (fixed via Facet). Not yet published or bundled. §9's dashboard criterion checked off | Chirag + Claude |
| 2026-07-22 | Dashboard exported and wired into the DAB bundle: Claude called `manage_dashboard` (`list`/`get`, read-only) to pull the already-built dashboard's `serialized_dashboard` into `src/dashboards/novalake_gold_analytics.lvdash.json`, then authored `resources/dashboard.yml` (`novalake_gold_analytics`, dev-only per `docs/adr/0003`) directly. `databricks bundle validate` passes. This was an explicit, one-off exception to `docs/checkpoint.md`'s "no agent workspace-write access until `v0.5`" rule — Chirag asked for it directly after being shown the tension; logged in checkpoint.md's revisit log, not a rule change. Not yet `bundle deploy`ed or published | Chirag + Claude |
| 2026-07-22 | Deployed and published, same explicit-exception basis as the export/wire step above. `bundle deploy` initially refused (would delete+recreate the dashboard, changing its ID/URL, since Lakeview dashboards can't rename or move in place). Root cause: `mode: development` on the `dev` target auto-injects a `[dev <user>] ` name prefix that can't be disabled via `presets.name_prefix: ""` (CLI v1.7.0 treats empty string as unset — a Go zero-value quirk) — also found this was silently double-prefixing the job's name via `novalake_medallion`'s own `[${bundle.target}]` convention. Fixed by dropping `mode: development` from `databricks.yml` and re-declaring its two presets that matter (`trigger_pause_status: PAUSED`, `pipelines_development: true`) explicitly; also added explicit `parent_path` to `resources/dashboard.yml` since the bundle's default (`.bundle/novalake/dev/resources`) didn't match the dashboard's actual location. `databricks bundle deployment bind novalake_gold_analytics 01f184fceb11160fa8d7982ad7bb345b` adopted the existing dashboard; `bundle deploy` then updated in place (`dashboard_id`/`create_time` confirmed unchanged after deploy). Published via `manage_dashboard(action="publish")` — live at `/sql/dashboardsv3/01f184fceb11160fa8d7982ad7bb345b`. §9's dashboard criterion fully checked off; sign-off still open | Chirag + Claude |
