# v0.4 Serving — Question → SQL Catalog

The shared, authored-once source of truth for both the Genie space (sample
questions) and the AI/BI dashboard (tile queries) — see `docs/04-serving.md`
Step 6.1. Designed once here so the two consumers can't independently drift
apart on the same business question.

Every query targets `novalake.gold.*` directly (no new dbt models). Every
query is checked against the 5 guardrails in `docs/04-serving.md` §4 before
being added below — the "Guardrail" line on each entry says which one(s)
applied and how.

**General principle used throughout:** a `metric_*` table's own grain
(`event_date`, `source`, sometimes `priority`) is the safe unit to query or
trend directly. Any question that rolls up *across* that grain (a quarter, a
half-year, "overall") must recompute from the underlying counts each metric
exposes — never average an already-computed rate or average column. Where a
question is a simple aggregate over raw rows (not an average-of-averages),
querying the `fct_*` table directly is simpler and just as correct.

---

## 1. Transactions

**Q: What's daily transaction volume and completion count, by source and currency?**
Guardrail: none needed — this is a direct grain-level read, not a rollup.
```sql
select event_date, source, currency_clean, transaction_count, completed_count, gross_amount_major
from novalake.gold.metric_transaction_volume
order by event_date
```

**Q: What was our approval rate in Q1 2026, across both sources?**
Guardrail: #5 (rate-averaging trap) — `approval_rate` is pre-computed per
`(event_date, source)`; a coarser-grain answer must recompute from
`completed_count`/`failed_count`, never `AVG(approval_rate)`.
```sql
select
    sum(completed_count) / nullif(sum(completed_count) + sum(failed_count), 0) as approval_rate
from novalake.gold.metric_approval_decline_rate m
join novalake.gold.dim_date d on m.event_date = d.date_day
where d.year = 2026 and d.quarter = 1
```

**Q: What's the total USD-normalized transaction volume this month, multiline only?**
Guardrail: #1 (fx blending) — USD totals only exist for `multiline`; never
add `ndjson` amounts into this figure, and never present it as "total volume"
without the multiline-only label.
```sql
select sum(gross_amount_usd) as gross_amount_usd_multiline_only
from novalake.gold.metric_transaction_volume_usd_multiline
where event_date >= date_trunc('month', current_date())
```

---

## 2. Refunds

**Q: What's our overall refund rate, and how does it vary by source?**
Guardrail: #3 (non-FK join) + #5 (rate averaging) — `refund_count` and
`completed_transaction_count` are independently aggregated at
`(event_date, source)` in the metric (never joined via
`original_transaction_id`, which is a random UUID); a period-level rate
recomputes from the two counts, not from an averaged `refund_rate` column.
```sql
select
    source,
    sum(refund_count) / nullif(sum(completed_transaction_count), 0) as refund_rate
from novalake.gold.metric_refund_rate
group by source
```

**Q: What are refunds issued for, broken down by reason?**
Guardrail: none — direct aggregate over `fct_refunds`, no cross-grain rollup.
```sql
select source, reason, count(*) as refund_count, sum(amount) as total_refunded
from novalake.gold.fct_refunds
group by source, reason
order by refund_count desc
```

---

## 3. Payouts

**Q: What's typical payout latency (p50/p90) by source and schedule status?**
Guardrail: none needed at this grain — direct read of `metric_payout_latency`.
```sql
select event_date, source, schedule_status, payout_count, avg_lead_days, p50_lead_days, p90_lead_days
from novalake.gold.metric_payout_latency
order by event_date
```

**Q: Which merchants have the most payouts on hold?**
Guardrail: none the schema needs curated for, but note `fct_payouts` has
**no `customer_id`** — this event type is merchant-centric only in both
generators; never attribute a payout to a customer.
```sql
select p.merchant_id, m.name, count(*) as held_count
from novalake.gold.fct_payouts p
left join novalake.gold.dim_merchants m on p.merchant_id = m.merchant_id
where p.schedule_status = 'held'
group by p.merchant_id, m.name
order by held_count desc
```

---

## 4. Support

**Q: What's our average ticket resolution time?**
Guardrail: #2 (support-metric blending) — `ndjson`-only; `multiline` never
had a `resolution_minutes` concept at all, so it's excluded from this query
entirely, not coalesced or defaulted.
```sql
select priority, avg(resolution_minutes) as avg_resolution_minutes
from novalake.gold.fct_support_tickets
where source = 'ndjson' and resolved = true
group by priority
```

**Q: What's our SLA breach rate?**
Guardrail: #2 (support-metric blending) + #5 (rate averaging) — companion,
not a substitute, for the question above; `multiline`-only, recomputed from
`breached_count`/`ticket_count`, never `AVG(sla_breach_rate)`.
```sql
select
    priority,
    sum(breached_count) / nullif(sum(ticket_count), 0) as sla_breach_rate
from novalake.gold.metric_support_sla_breach_rate_multiline
group by priority
```
**These two answers are always reported side by side, never merged into one
"support performance" number** — there is no valid conversion between
elapsed-time and target/breach-flag concepts (see `docs/03-gold.md` §4).

---

## 5. Reviews

**Q: Which merchants have the best/worst average rating?**
Guardrail: #5 (rate averaging) — `avg_rating`/`verified_purchase_rate` are
real per-row aggregates already correctly computed in the metric (not an
average-of-averages, since the metric's grain *is* `merchant_id`); safe to
read directly **at merchant grain**.
```sql
select m.name, m.category, r.avg_rating, r.rating_count, r.verified_purchase_rate
from novalake.gold.metric_review_ratings_by_merchant r
join novalake.gold.dim_merchants m on r.merchant_id = m.merchant_id
order by r.avg_rating desc
```

**Q: What's the average rating by merchant category?**
Guardrail: #5 (rate averaging) — this rolls up *past* merchant grain, so
both `avg_rating` and `verified_purchase_rate` must be recomputed as
count-weighted means (`sum(x * rating_count) / sum(rating_count)`), never
`AVG()` of the per-merchant columns — otherwise every merchant counts
equally regardless of how many ratings it actually has.
```sql
select
    m.category,
    sum(r.avg_rating * r.rating_count) / nullif(sum(r.rating_count), 0) as avg_rating,
    sum(r.verified_purchase_rate * r.rating_count) / nullif(sum(r.rating_count), 0) as verified_purchase_rate
from novalake.gold.metric_review_ratings_by_merchant r
join novalake.gold.dim_merchants m on r.merchant_id = m.merchant_id
group by m.category
```

---

## 6. Risk / Fraud

**Q: What fraction of transactions were risk-flagged, and separately, what
fraction of risk alerts led to an auto-block?**
Guardrail: #3 (non-FK-shaped join risk, generalized) — no field links
`risk.alert` events to specific transactions in either generator (confirmed:
no `transaction_id` in `build_risk_alert`), so these are two independent
rates from two independent fact tables, joined only on `(event_date,
source)` — never presented as one blended "fraud rate." Also #5 (rate
averaging) if rolled up across dates.
```sql
select
    source,
    sum(risk_flagged_count) / nullif(sum(transaction_count), 0) as txn_risk_flagged_rate,
    sum(auto_blocked_count) / nullif(sum(alert_count), 0) as alert_auto_block_rate
from novalake.gold.metric_fraud_signals
group by source
```

---

## 7. Auth Sessions

**Q: What's our authentication success rate, by MFA usage?**
Guardrail: none the schema needs curating for; there's no `metric_*` table
for this domain yet, so the rate is computed directly from `fct_auth_sessions`
row counts (a genuine per-row rate, not a rollup of a pre-computed one).
```sql
select
    mfa_used,
    count(*) filter (where result = 'success') / nullif(count(*), 0) as success_rate,
    count(*) as session_count
from novalake.gold.fct_auth_sessions
group by mfa_used
```

---

## 8. KYC Verifications

**Q: What fraction of KYC verifications land in each status?**
Guardrail: none the schema needs curating for — but `risk_score`'s
nullability and scale are **not** tested in `_gold.yml` (unlike every enum
column here), and both sources are blended into one figure below. Treat any
`avg(risk_score)` reading as unverified until confirmed against
`data/generators/` that both generators emit the same scale; kept split by
`source` here specifically so a scale mismatch would show up as a visible
divergence rather than being silently averaged away.
```sql
select
    source,
    status,
    count(*) as verification_count,
    count(*) / sum(count(*)) over (partition by source) as status_share,
    avg(risk_score) as avg_risk_score
from novalake.gold.fct_kyc_verifications
group by source, status
order by source, verification_count desc
```

---

## Cross-domain

**Q: Give me a merchant overview — reviews, transaction volume, payout status.**
Guardrail: #4 (dimension sparsity) — `dim_merchants` attributes come from
`int_multiline_merchants` only; in this dataset that happens to be fully
populated (100/100), but the join is written defensively (LEFT JOIN,
`has_multiline_profile` flag) the same way the dimension itself is, not
assuming completeness structurally.

**Fan-out foot-gun:** joining `fct_transactions` and `fct_reviews` to
`dim_merchants` in the *same* query is a one-to-many × one-to-many join —
each merchant's transaction rows are cross-multiplied against its review
rows. `count(distinct ...)` happens to dedupe correctly today, but any
future non-distinct measure added beside it (`sum(amount)`, `avg(rating)`,
plain `count(*)`) would silently inflate by the other table's cardinality.
Pre-aggregate each fact in its own CTE first, so no such column can ever be
added unsafely:
```sql
with txns as (
    select merchant_id, count(*) as transaction_count
    from novalake.gold.fct_transactions
    group by merchant_id
),
reviews as (
    select merchant_id, count(*) as review_count
    from novalake.gold.fct_reviews
    group by merchant_id
)
select
    m.merchant_id,
    m.name,
    m.category,
    m.has_multiline_profile,
    coalesce(t.transaction_count, 0) as transaction_count,
    coalesce(r.review_count, 0) as review_count
from novalake.gold.dim_merchants m
left join txns t on m.merchant_id = t.merchant_id
left join reviews r on m.merchant_id = r.merchant_id
```
Note: `fct_transactions.merchant_id` is ~2% null on the `ndjson` side (the
inline `merchant` struct is itself nullable by generator design) — those
transactions are silently excluded from any merchant-grouped rollup, which
is expected, not a join bug.

**Q: Give me a customer overview — transactions, support tickets, whether we
have an enriched profile for them.**
Guardrail: #4 (dimension sparsity), demonstrated on the dimension where it
actually bites — unlike `dim_merchants` (100/100 populated in this dataset),
`dim_customers.has_multiline_profile` is true for only 296 of 6,296 rows by
deliberate design (`int_multiline_customers` samples 40-70 customers/page,
not the full pool). Any consumer of `full_name`/`addresses`/`loyalty`/
`consents` must expect NULL for the large majority of customers — not a
data-quality gap to chase down. Same pre-aggregate-then-join pattern as the
merchant query, for the same fan-out reason.
```sql
with txns as (
    select customer_id, count(*) as transaction_count
    from novalake.gold.fct_transactions
    group by customer_id
),
tickets as (
    select customer_id, count(*) as ticket_count
    from novalake.gold.fct_support_tickets
    group by customer_id
)
select
    c.customer_id,
    c.has_multiline_profile,
    c.full_name,
    coalesce(t.transaction_count, 0) as transaction_count,
    coalesce(k.ticket_count, 0) as ticket_count
from novalake.gold.dim_customers c
left join txns t on c.customer_id = t.customer_id
left join tickets k on c.customer_id = k.customer_id
```

---

## Genie space table-scope implication

Every query above only ever needs: `dim_date`, `dim_customers`,
`dim_merchants`, all 8 `fct_*` tables, and all 9 `metric_*` tables — but
**never** `fct_refunds.original_transaction_id` or
`fct_support_tickets.related_transaction_id`. Per `docs/04-serving.md` Step
6.2, those two columns are excluded from the Genie space's table scope
entirely, not just avoided by convention here.

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-21 | Initial catalog drafted: 8 domains + 1 cross-domain question, each checked against the 5 guardrails in `docs/04-serving.md` §4 | Chirag + Claude |
| 2026-07-21 | Plan reviewed by Opus before implementation (five corrections made: added a category-level rollup example showing the rate-averaging fix for review ratings, fixed the merchant-overview fan-out risk by pre-aggregating each fact in its own CTE before joining, made Auth/KYC questions actually return the rate they ask for, flagged KYC's `avg(risk_score)` as resting on an unverified nullability/scale assumption and split it by `source`, and added the missing customer-overview question — the sparse dimension guardrail #4 was previously only demonstrated on `dim_merchants`, which is 100% populated in this dataset, not `dim_customers`, which is genuinely sparse) — all five folded in above | Chirag + Claude |
