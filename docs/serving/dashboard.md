# v0.4 Serving — Dashboard Spec

Implements `docs/04-serving.md` Step 6.3. Per the plan's third correction,
the dataset SQL below (not a hand-authored `.lvdash.json`) is the reviewed
unit here. The `databricks-aibi-dashboards` skill's own mandatory workflow —
`get_table_stats_and_schema` → write SQL → **test every query via
`execute_sql`** → build the widget/layout JSON → `manage_dashboard(action=
"create_or_update")` — requires workspace access at the test/build/deploy
steps. Per `docs/checkpoint.md`, those steps happen when you (or a future
session you explicitly authorize) run the skill's workflow against this
spec — not in this hands-off `v0.4` planning session. What's below is the
input to that workflow: vetted datasets and a layout plan, ready to hand to
it.

## Datasets

One dataset per domain, single query each (CTEs allowed, no multi-statement
SQL), business logic and aliases already in the `SELECT` per the skill's
rules. Adapted from `docs/serving/question_catalog.md` — same guardrails,
widget-ready column names, date truncation added for time-series charts.

### `ds_transaction_volume`
```sql
select
    date_trunc('DAY', event_date) as day,
    source,
    currency_clean,
    transaction_count,
    completed_count,
    gross_amount_major
from novalake.gold.metric_transaction_volume
```

### `ds_approval_decline_trend`
```sql
select
    date_trunc('DAY', m.event_date) as day,
    m.source,
    m.completed_count,
    m.failed_count,
    m.approval_rate,
    m.decline_rate
from novalake.gold.metric_approval_decline_rate m
```
Note: this dataset's `approval_rate` is safe for a **daily trend line**
(one value per grain row). Never feed it into a KPI counter that aggregates
across days — that would average the rate (guardrail #5). Use
`ds_approval_decline_rollup` below for any coarser-grain KPI.

### `ds_approval_decline_rollup` (KPI counter — quarter-to-date)
```sql
with latest as (
    select max(date_day) as max_date from novalake.gold.dim_date
)
select
    sum(completed_count) / nullif(sum(completed_count) + sum(failed_count), 0) as approval_rate_qtd
from novalake.gold.metric_approval_decline_rate m
join novalake.gold.dim_date d on m.event_date = d.date_day
cross join latest l
where d.year = year(l.max_date) and d.quarter = quarter(l.max_date)
```
**Bug found and fixed during build (2026-07-21):** the original version
filtered on `year(current_date())`/`quarter(current_date())` — literally
"today," which in the deployment environment was 2026-07-21 (Q3 2026). The
dataset only covers 2026-01-01 through 2026-06-15, so that filter matched
zero rows and the counter rendered `null`. Fixed by anchoring "current
quarter" to the latest date actually present in `dim_date` instead of the
wall clock, so the KPI stays meaningful regardless of when the dashboard is
viewed relative to a fixed historical synthetic dataset.

### `ds_refund_rate_by_source`
```sql
select
    source,
    sum(refund_count) as refund_count,
    sum(completed_transaction_count) as completed_transaction_count,
    sum(refund_count) / nullif(sum(completed_transaction_count), 0) as refund_rate
from novalake.gold.metric_refund_rate
group by source
```

### `ds_payout_latency`
```sql
select
    date_trunc('DAY', event_date) as day,
    source,
    schedule_status,
    payout_count,
    avg_lead_days,
    p50_lead_days,
    p90_lead_days
from novalake.gold.metric_payout_latency
```
**Chart-building note (found during build, 2026-07-21):** this dataset's
grain is `(day, source, schedule_status)` — up to 4 `schedule_status` rows
per `(day, source)`. A chart that only splits by `source` (Color) and plots
`p50_lead_days`/`p90_lead_days` will silently **sum percentiles across the 4
statuses** by default, which is meaningless (percentiles aren't additive
across categories the way counts are — unlike `payout_count`, which sums
correctly). Any chart on this dataset must add `schedule_status` as a
**Facet** (or otherwise split by it) so each line represents one true
`(day, source, schedule_status)` grain point, never a cross-status sum.

### `ds_support_resolution_time` (ndjson only — never blended with SLA breach)
```sql
select priority, avg(resolution_minutes) as avg_resolution_minutes
from novalake.gold.fct_support_tickets
where source = 'ndjson' and resolved = true
group by priority
```

### `ds_support_sla_breach_rate` (multiline only — companion, not a substitute)
```sql
select
    priority,
    sum(breached_count) as breached_count,
    sum(ticket_count) as ticket_count,
    sum(breached_count) / nullif(sum(ticket_count), 0) as sla_breach_rate
from novalake.gold.metric_support_sla_breach_rate_multiline
group by priority
```

### `ds_fraud_signals`
```sql
select
    source,
    sum(risk_flagged_count) / nullif(sum(transaction_count), 0) as txn_risk_flagged_rate,
    sum(auto_blocked_count) / nullif(sum(alert_count), 0) as alert_auto_block_rate
from novalake.gold.metric_fraud_signals
group by source
```

### `ds_ratings_by_category`
```sql
select
    m.category,
    sum(r.avg_rating * r.rating_count) / nullif(sum(r.rating_count), 0) as avg_rating,
    sum(r.rating_count) as rating_count
from novalake.gold.metric_review_ratings_by_merchant r
join novalake.gold.dim_merchants m on r.merchant_id = m.merchant_id
group by m.category
```

### `ds_auth_success_rate`
```sql
select
    mfa_used,
    count(*) filter (where result = 'success') / nullif(count(*), 0) as success_rate,
    count(*) as session_count
from novalake.gold.fct_auth_sessions
group by mfa_used
```

### `ds_kyc_status_share`
```sql
select
    source,
    status,
    count(*) as verification_count,
    count(*) / sum(count(*)) over (partition by source) as status_share
from novalake.gold.fct_kyc_verifications
group by source, status
```

All ≤8-distinct-value dimensions (`source`=2, `currency_clean`≤7,
`schedule_status`=4, `priority`=4, `mfa_used`=2, `status`≤4) — within the
skill's chart cardinality guidance, no Top-N bucketing needed.

## Page / widget layout plan

**Page 1 — Overview**
| y | Widget | Type | Width | Height | Dataset |
|---|--------|------|-------|--------|---------|
| 0 | "NovaLake Gold Analytics" | Text | 12 | 1 | — |
| 1 | Subtitle | Text | 12 | 1 | — |
| 2 | Approval rate (QTD) | Counter | 4 | 3 | `ds_approval_decline_rollup` |
| 2 | Refund rate (by source) | Table | 4 | 3 | `ds_refund_rate_by_source` |
| 2 | Fraud signals | Table | 4 | 3 | `ds_fraud_signals` |
| 5 | "Trends" | Text | 12 | 1 | — |
| 6 | Transaction volume by source | Line | 6 | 5 | `ds_transaction_volume` |
| 6 | Approval/decline trend | Line | 6 | 5 | `ds_approval_decline_trend` |

**Page 2 — Payouts & Support**
| y | Widget | Type | Width | Height | Dataset |
|---|--------|------|-------|--------|---------|
| 0 | Payout latency (p50/p90), faceted by `schedule_status` | Line | 6 | 5 | `ds_payout_latency` |
| 0 | Payout count by status | Bar | 6 | 5 | `ds_payout_latency` |
| 5 | "Support (two separate metrics — never blended)" | Text | 12 | 1 | — |
| 6 | Avg resolution time (ndjson) | Bar | 6 | 5 | `ds_support_resolution_time` |
| 6 | SLA breach rate (multiline) | Bar | 6 | 5 | `ds_support_sla_breach_rate` |

**Page 3 — Reviews, Auth & KYC**
| y | Widget | Type | Width | Height | Dataset |
|---|--------|------|-------|--------|---------|
| 0 | Avg rating by category | Bar | 6 | 5 | `ds_ratings_by_category` |
| 0 | Auth success rate by MFA | Bar | 6 | 5 | `ds_auth_success_rate` |
| 5 | KYC status share by source | Table | 12 | 6 | `ds_kyc_status_share` |

Every row sums to width 12; counters at height 3, charts at height 5, per
the skill's sizing guidance. The Support page's section header explicitly
names the non-blending rule so it's visible in the dashboard itself, not
just in this doc.

## Build status (2026-07-21)

Built by hand in the workspace (Chirag, guided step by step by Claude — no
`manage_dashboard`/`execute_sql` calls made), as "NovaLake Gold Analytics."
All 11 datasets created and verified to return real rows; 3 pages
(**Overview**, **Payouts & Support**, **Reviews, Auth & KYC**) built per the
layout plan above, with two real issues found and fixed along the way (see
the notes on `ds_approval_decline_rollup` and `ds_payout_latency` above).
Every other widget's scale/range was sanity-checked (rates 0–1, ratings
1–5, no unexplained negative axes) before being accepted. Exported, wired
into the bundle, deployed, and published 2026-07-22 (see "DAB wiring"
below). Live at `/sql/dashboardsv3/01f184fceb11160fa8d7982ad7bb345b`.

## DAB wiring (done 2026-07-22)

The `.lvdash.json` was exported from the workspace (`manage_dashboard`,
`get` action — read-only) to `src/dashboards/novalake_gold_analytics.lvdash.json`,
then wired into the bundle the same way `resources/dbt_job.yml` already is:

```yaml
# resources/dashboard.yml
resources:
  dashboards:
    novalake_gold_analytics:
      display_name: "NovaLake Gold Analytics"
      parent_path: /Workspace/Users/chiragvenkatesh92@gmail.com
      file_path: ../src/dashboards/novalake_gold_analytics.lvdash.json
      warehouse_id: ${var.warehouse_id}
      dataset_catalog: ${var.catalog}
      dataset_schema: gold
```
Both `display_name` and `parent_path` had to match the existing dashboard
*exactly* — no `[${bundle.target}]` prefix, no default bundle-managed
folder — because Lakeview dashboards can't rename or move in place; any
mismatch makes `bundle deploy` delete and recreate the dashboard (new ID,
new URL) instead of updating it. Getting there also required dropping
`mode: development` from `databricks.yml`'s `dev` target, since its
automatic `[dev <user>] ` name prefix can't be suppressed via
`presets.name_prefix: ""` (a CLI v1.7.0 quirk — empty string is
indistinguishable from unset). See `docs/checkpoint.md`'s 2026-07-22
revisit-log entry and `docs/04-serving.md`'s Changelog for the full
sequence. `databricks bundle deployment bind novalake_gold_analytics
01f184fceb11160fa8d7982ad7bb345b` adopted the existing dashboard before
`bundle deploy`, confirmed by `dashboard_id`/`create_time` being unchanged
after deploy. Per `docs/adr/0003` (dev-only bundle target until `v0.5`),
this stays `dev`-only.

This export, wiring, deploy, and publish were all done by Claude directly
(`manage_dashboard` calls plus authoring `resources/dashboard.yml` and
editing `databricks.yml`), a one-off exception to `docs/checkpoint.md`'s
"no agent workspace-write access until `v0.5`" rule — Chirag asked for each
step explicitly after the tension was flagged for each. Logged in
`docs/checkpoint.md`'s revisit log (2026-07-22) as a deliberate exception,
not a rule change; the dashboard's actual content (datasets, pages,
widgets) was still built by hand on 2026-07-21 — this only exported,
wired, deployed, and published the existing artifact.

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-21 | Initial dashboard dataset + layout spec drafted from `docs/serving/question_catalog.md`, following the `databricks-aibi-dashboards` skill's dataset/widget/cardinality rules; full JSON deliberately deferred to the skill's own validation workflow, not hand-authored here | Chirag + Claude |
| 2026-07-21 | Built by hand in the workspace (Chirag, guided step by step by Claude — no MCP write calls). All 11 datasets and 3 pages created per the plan. 2 bugs found and fixed during build: `ds_approval_decline_rollup`'s `current_date()` filter matched zero rows against the historically-bounded dataset (fixed to anchor on the latest date in `dim_date`); the Payment Latency chart was silently summing percentiles across `schedule_status` (fixed by adding it as a Facet). Not yet published or exported/bundled | Chirag + Claude |
| 2026-07-22 | Dashboard exported (`manage_dashboard` read calls) to `src/dashboards/novalake_gold_analytics.lvdash.json` and wired into the bundle via `resources/dashboard.yml`; `databricks bundle validate` passes. One-off exception to `docs/checkpoint.md`'s hands-on rule, explicitly requested and logged there. Not yet `bundle deploy`ed or published | Chirag + Claude |
| 2026-07-22 | Deployed and published. `bundle deploy` initially refused (would delete+recreate, changing ID/URL); root-caused to `mode: development`'s unsuppressable name prefix plus a `parent_path` mismatch against the bundle's default resource folder. Fixed both in `databricks.yml`/`resources/dashboard.yml` (see "DAB wiring" above), then `databricks bundle deployment bind` adopted the existing dashboard and `bundle deploy` updated it in place. Published via `manage_dashboard(action="publish")`. Live at `/sql/dashboardsv3/01f184fceb11160fa8d7982ad7bb345b` | Chirag + Claude |
