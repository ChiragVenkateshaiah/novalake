# v0.4 Serving — Genie Space Spec

Implements `docs/04-serving.md` Step 6.2. This is the reviewable draft; per
`docs/checkpoint.md` (phases `v0.0`–`v0.4` stay hands-on), creating the actual
space in the workspace — via the Databricks UI, CLI, or the `manage_genie`
MCP tool — is a step you run yourself, not something done from this session.

## Display name & description

**Display name:** `NovaLake Gold Analytics`

**Description** (space-level, shown to users):
> Explore payments, refunds, payouts, support, reviews, risk, auth, and KYC
> data across NovaLake's Gold layer. Data comes from two independently
> generated sources (`ndjson` and `multiline`) that share real customer/
> merchant identities but keep some concepts deliberately separate — see
> Instructions below before trusting a blended number.

## Table scope

All 20 Gold models, **with one manual exclusion step required at creation
time** (see caveat below):

- Dimensions: `dim_date`, `dim_customers`, `dim_merchants`
- Facts: `fct_transactions`, `fct_refunds`, `fct_payouts`,
  `fct_support_tickets`, `fct_reviews`, `fct_risk_alerts`,
  `fct_auth_sessions`, `fct_kyc_verifications`
- Metrics: `metric_transaction_volume`,
  `metric_transaction_volume_usd_multiline`, `metric_approval_decline_rate`,
  `metric_refund_rate`, `metric_fraud_signals`,
  `metric_support_resolution_time`,
  `metric_support_sla_breach_rate_multiline`,
  `metric_review_ratings_by_merchant`, `metric_payout_latency`

**Column-exclusion caveat.** Per `docs/04-serving.md` Step 6.2, this space
must exclude `fct_refunds.original_transaction_id` and
`fct_support_tickets.related_transaction_id` from Genie's visibility — both
are random UUIDs, not real FKs, and their presence invites a plausible-looking
but wrong join to `fct_transactions.event_id`. The `manage_genie` MCP tool's
`table_identifiers`/`column_configs` fields (per the `databricks-genie`
skill) support per-column *format/entity-matching* hints, not exclusion —
column-level exclusion has to be done via the workspace UI's per-table
column picker when the space is created or edited by hand. **Do not skip
this step** — it's the one guardrail that curation, not instructions, has to
carry.

## General instructions (space-level)

Paste as the space's "Instructions" field:

> 1. Never combine fx-normalized USD totals (only exist for `multiline`) with
>    native-currency totals from `ndjson` into one figure. Label any USD
>    total as multiline-only.
> 2. Never blend support-ticket performance across sources.
>    `resolution_minutes` (real elapsed time) exists only for `ndjson`;
>    `sla_breached`/`sla_target_minutes` (target/breach flag) exist only for
>    `multiline`. Always report these as two separate answers, never one
>    "support performance" number.
> 3. Never join `fct_refunds` or `fct_support_tickets` to `fct_transactions`
>    on `original_transaction_id` or `related_transaction_id` — both are
>    independently random UUIDs in both source generators, not real foreign
>    keys. Use aggregate ratios grouped by `(event_date, source)` instead.
> 4. `dim_customers.has_multiline_profile` is false for most rows (296 of
>    6,296) by deliberate dataset design — this is expected sparsity, not a
>    data quality problem. Don't describe it as missing or broken data.
> 5. Every `metric_*` table's rate column (`approval_rate`, `decline_rate`,
>    `refund_rate`, `sla_breach_rate`, `verified_purchase_rate`) is
>    pre-computed at a specific grain (`event_date`, `source`, sometimes
>    `priority`). Any question spanning a coarser grain (a quarter, a
>    category, "overall") must recompute the rate from the underlying counts
>    each metric table also exposes — never average the rate column itself.
> 6. `fct_payouts` has no `customer_id` — this event type is merchant-centric
>    only in both sources; never attribute a payout to a customer.
> 7. `fct_transactions.merchant_id` is ~2% null on the `ndjson` side by
>    design (the inline `merchant` struct is itself nullable) — merchant-
>    grouped rollups will silently exclude those rows; this is expected.

## Certified example question → SQL pairs

The highest-leverage lever for guardrail compliance: pin the SQL for the
questions most likely to trigger the rate-averaging or non-FK-join traps, so
Genie answers these from a trusted, tested query rather than generating SQL
freehand. Pulled directly from `docs/serving/question_catalog.md` (already
reviewed by Opus):

| Question | SQL source |
|---|---|
| "What was our approval rate last quarter?" | `question_catalog.md` §1, Q2 |
| "What's our overall refund rate by source?" | `question_catalog.md` §2, Q1 |
| "What's our SLA breach rate by priority?" | `question_catalog.md` §4, Q2 |
| "What's our txn risk-flagged rate and alert auto-block rate by source?" | `question_catalog.md` §6 |
| "What's the average rating by merchant category?" | `question_catalog.md` §5, Q2 |
| "What's our authentication success rate by MFA usage?" | `question_catalog.md` §7 |

(Full SQL text lives in the catalog file — not duplicated here, to keep one
source of truth per Step 6.1.)

## Sample questions (shown in the Genie UI)

Broader set, covering domains without a certified pair too — drawn from
`docs/serving/question_catalog.md` in full:

1. What's daily transaction volume by source and currency?
2. What was our approval rate last quarter?
3. What's our total USD-normalized transaction volume this month (multiline only)?
4. What's our overall refund rate, and how does it vary by source?
5. What are refunds issued for, broken down by reason?
6. What's typical payout latency (p50/p90) by source and schedule status?
7. Which merchants have the most payouts on hold?
8. What's our average ticket resolution time?
9. What's our SLA breach rate?
10. Which merchants have the best/worst average rating?
11. What's the average rating by merchant category?
12. What fraction of transactions were risk-flagged, and what fraction of alerts led to an auto-block?
13. What's our authentication success rate by MFA usage?
14. What fraction of KYC verifications land in each status, by source?
15. Give me a merchant overview — reviews, transaction volume.
16. Give me a customer overview — transactions, support tickets, whether we have an enriched profile for them.

## Deployment checklist (for you to run, not this session)

- [ ] Create the space via UI/CLI/`manage_genie` with the table scope above
- [ ] **Manually exclude `original_transaction_id` and
      `related_transaction_id`** from the space's column visibility
- [ ] Paste the General Instructions block above
- [ ] Add the certified example question/SQL pairs
- [ ] Add the sample questions list
- [ ] Test each certified pair returns the expected guardrail-respecting
      answer before considering this step done (`docs/04-serving.md` §9)

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-21 | Initial Genie space spec drafted from `docs/serving/question_catalog.md`, using the `databricks-genie` skill's `serialized_space`/`table_identifiers`/`example_question_sqls` model to shape the artifact | Chirag + Claude |
