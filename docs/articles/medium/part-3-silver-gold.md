<!--
MEDIUM METADATA — Part 3 of 8
Title:      Silver and Gold
Subtitle:   Two pipelines describing the same business, deliberately never unified — and conformance verified per field, not assumed. (126 chars)
Cover:      ../poster/part-3-silver-gold.png
SEO title:  Silver and Gold: conformance verified per field (46)
SEO desc:   81 dbt models, four ways to silently lose rows, and a refactor check row counts cannot do. The medallion middle, with the mistakes left in. (141)
Tags:       dbt, Data Engineering, Databricks, SQL, Data Modeling
Source:     docs/articles/novalake-full-story.md — lines 120-202, verbatim
-->

# Silver and Gold

### Two pipelines that describe the same business, deliberately never unified — and why conformance is a property you verify per field, not a thing you assume

*Part 3 of 8 in **The platform is the only source of truth**, a build log of a Databricks lakehouse taken end to end on Free Edition.*
*← Previous: [Bronze, and the confidently wrong fix](LINK-PART-2) · Next: [Serving and CI/CD](LINK-PART-4) →*

---

**Where we are.** [Part 2](LINK-PART-2) ended with Bronze landed — 7,105 rows, 51 inferred leaf fields, two of them collapsed to string by Spark's own inference — and a schema-drift audit that sorted the damage into five distinct problem categories. Those five categories are the scope of this phase. Silver resolves them; Gold conforms what's left.

## The architecture, and where this part sits

The cover strip lights **SILVER → GOLD** — the two middle stages, and the only place in the whole build where the shape of the architecture is itself the main finding.

Silver is not one pipeline. It is **two**, running side by side, and the diagram's single "SILVER" box hides that deliberately-doubled structure. The NDJSON source and the multiline source get completely separate model lineages: separate staging models, separate dedup, separate per-event-type transforms, separate dead-letter splits. They never touch each other. Everything is a dbt model — SQL, version-controlled, tested — materialized as views on top of the Bronze Delta table.

Gold is where the two branches finally converge, and the convergence is selective rather than wholesale. It has three shapes of model:

- **Conformed dimensions** (`dim_customers`, `dim_merchants`, `dim_date`) — built only where identity genuinely conforms across the two sources.
- **Facts** (`fct_transactions`, `fct_refunds`, `fct_support_tickets`, …) — each unioning the two branches, but only after flattening to shared scalar columns.
- **Metric rollups** (`metric_*`) — pre-aggregated at a declared grain, each one carrying the underlying counts alongside its rates.

The design rule that runs through both stages: **a union is a claim that two things are the same, and every such claim gets verified per field rather than assumed from a matching column name.** Silver keeps the two sources apart because their payload shapes genuinely differ. Gold joins them only where their identifiers genuinely conform — checked against the generator source code, not inferred from the schema.

That third model shape, the metric rollups, exists specifically to serve the layer in Part 4, where the consumer stops being a human.

---

## Silver — two pipelines that describe the same business, deliberately never unified

Silver was the largest phase by a wide margin: all 10 event types across both raw sources, delivered as eight sequential increments, each reviewed by a second model before implementation and committed independently. It ended at **81 dbt models**, **175 of 179 tests passing** with 4 intentional warnings.

The architectural decision that shaped everything: the NDJSON and multiline pipelines stay **completely parallel and never unify** until Gold. They describe the same business events. They have no shared `ingested_at` field, structurally incompatible payload shapes, and different dedup tie-breaks. Forcing them into one pipeline would have meant a union of every difference, defended by `case` expressions, at every stage.

**NDJSON path:** `raw_events` → `stg_raw_events` → `int_events_deduped` (generic dedup, envelope drift, `customer_id_resolved`) → eight per-event-type `int_<type>` / `_clean` / `_dlq` triples → child explode models.

**Multiline path:** the first transform is an explode, because reading a pretty-printed JSON array with `multiLine=true` returns **one row per page** — 9 rows for the whole dataset. The actual events live inside `data.events`. So: `raw_events_multiline` (9 rows) → `stg_raw_events_multiline` → `int_multiline_events` and `int_multiline_partial_failures` → `int_multiline_events_deduped` → eight triples → child explodes including two-level nesting → cross-page dimension models (`int_multiline_merchants`, `_customers`, `_fx_rates`) → `int_multiline_transactions_fx_applied` → a record-count reconciliation model.

### The generic-versus-scoped split

Envelope-level drift generalizes cleanly across every event type: dedup, timestamp resolution, source-shape resolution, key-renamed identifiers. Payload-level drift does not — `transaction.*`'s `risk`-struct-collapse and `amount_minor` int-vs-string problems have nothing to do with `support.ticket`'s array-of-messages problem. Building a generic payload resolver would have cost more than it saved. So the generic layer does envelope work and computes one flag for everything:

```sql
case
    when resolved_event_timestamp is null then 'null'
    when resolved_event_timestamp = timestamp('1970-01-01T00:00:00Z') then 'epoch_zero'
    when resolved_event_timestamp = timestamp('2099-12-31T00:00:00Z') then 'far_future'
    else 'ok'
end as event_timestamp_quality
```

...and then the DLQ split is mechanically identical for every event family, two one-line models:

```sql
-- int_<type>_clean:  where event_timestamp_quality = 'ok'
-- int_<type>_dlq:    where event_timestamp_quality != 'ok'
```

Exhaustive and exclusive by construction, verified by direct count everywhere: `transaction.*` split 3,042 + 150 = 3,192; multiline `transaction.*` split 1,688 + 88 = 1,776. **Array-explode children always read from `_clean`, never from `_dlq`** — quarantined rows shouldn't fan out into child tables.

That pattern is boring on purpose, and it's the thing DLT's headline data-quality primitive turned out not to be able to replace. More on that in Part 6.

### Four ways to silently lose or corrupt rows

**`LATERAL VIEW OUTER posexplode` versus plain `posexplode`.** Arrays in this dataset come in three flavors: populated, genuinely empty (`[]`), and missing entirely (`null`). Plain `posexplode` drops the row when the array is empty or null. Without `OUTER`, roughly **18–19% of clean transactions would have silently vanished** from `int_transaction_line_items` — no error, no warning, just a smaller table. Guaranteed-non-empty arrays got plain `posexplode`; everything else got `OUTER`.

**FX conversion direction.** The multiline source carries `fx_rates` with the semantics `{base: USD, quote: X, rate: R}`, meaning *1 USD = R units of X*. Converting quote→USD therefore **divides** by the rate. Getting that backwards produces plausible-looking numbers that are wrong by orders of magnitude and never errors. I hand-verified against the generator source and then against real rows: INR `2893 / 99.5142 ≈ 29`, CAD `69197 / 86.3267 ≈ 802`. Separately, the generator never emits a rate row for USD itself — it's the base currency — so this is a `LEFT JOIN` plus `coalesce(rate, 1.0)`, never an `INNER JOIN`. An inner join here silently deletes every USD transaction.

**A join at the wrong grain fans out.** An early draft of the record-count reconciliation model joined unaggregated per-page events to per-page failures directly on `page`, inflating both counts. Caught in review before it ran, by pre-aggregating each side to page grain first.

**Reconciliation grain, more subtly.** The generator computes `export_metadata.record_counts.events` *after* appending within-page replay duplicates. Reconciling against the deduped count would have silently mixed the generator's intentional reconciliation delta with an unrelated ~1.4% dedup effect, producing a "discrepancy" that was really two effects stacked. Caught in review before implementation.

### The dynamic-key-map trap that mostly wasn't

The multiline source's data dictionary warns about dynamic-key maps as a schema-explosion trap: `metadata`, `balances`, `currency_catalog`, `checksums`, `customers[].consents`, `merchants[].tax_ids`, `device.sensors`. When I actually inspected the inferred schema, **every one of them landed as a bounded, named-field struct** — because this generator's "dynamic" maps draw from a fixed key universe. The trap wasn't there.

The right answer wasn't "so ignore it." It was a principled split that a review pass reframed from an earlier, weaker "pick one to demonstrate" draft: reconstruct **open-vocabulary / lookup-keyed** fields (`metadata`, `device.sensors`, `line_items[].attributes`, `balances`) as genuine `MAP<STRING,STRING>` via a `to_json` + `from_json` round-trip, so they don't break when a new key appears; leave **closed-enum** fields (`tax_ids`, `consents`, `checksums`, `currency_catalog`, `reactions`) as direct struct access, because they're not maps, they're records that happen to look like maps.

### Cross-page dimensions

Roughly 99 `merchant_id`s appear on multiple pages with drifted name casing or category. `as_of_page` gives a real ordering signal, so merchants resolve latest-wins: `row_number() over (partition by merchant_id order by as_of_page desc)`. Customers have no real cross-page linkage, so they get an arbitrary but *deterministic* tie-break (`order by customer_id`) — which is a different thing from latest-wins and worth naming as such rather than copy-pasting the merchant pattern. `int_multiline_merchants` landed at exactly 100 rows (the full `mer_1000`–`mer_1099` pool); `int_multiline_fx_rates` at exactly 54 (6 non-USD currencies × 9 pages).

### The refactor verification that row counts can't do

Increment 0 refactored `int_transactions` onto the new generic envelope layer. Row counts matched. All tests passed. That proves nothing — a refactor can preserve row count and test outcomes while corrupting values inside rows.

So the verification was a **full-row `EXCEPT` diff in both directions, before versus after: 0 rows either way.** That was the single most valuable catch of the second-model review pass in this phase, and it's now my default for any refactor of a transformation model.

---

## Gold — conformance is a property you verify per field, not a thing you assume

Gold added **20 models**: 3 conformed dimensions, 8 facts, 9 metric rollups. The full project then built as 101 models together with **295/302 tests passing, 7 WARN, 0 ERROR** — every warning the intentional `"US$"` currency case.

The core question at this layer: the two sources were generated independently. Which of their identifiers are *genuinely* the same thing?

**Identity conforms; shape doesn't.** Both generators draw `customer_id` from `cust_10000`–`cust_19999` and `merchant_id` from `mer_1000`–`mer_1099`. Verified against the generator source, not assumed. So the identities are real and unioning them into a conformed dimension is legitimate — even though the payload shapes around them stayed deliberately unreconciled all the way through Silver.

**Sparsity should be explicit and tested, not implicit.** `int_multiline_customers` samples only 40–70 customers per page, so most `dim_customers` rows have no multiline profile at all: **296 of 6,296**. Rather than let that look like a data-quality gap, `dim_customers` carries a `has_multiline_profile` boolean, tested. `dim_merchants` uses the *identical* defensive pattern and happens to come out fully populated at 100/100 — because multiline sampling covers ~60% of merchants per page across 9 pages, which covers the pool. That's a property of this dataset, not a structural guarantee, and the pattern stays defensive precisely because the difference is luck.

**`UNION ALL` across differently-shaped structs is a silent misalignment waiting to happen.** Multiline's `payment_method` struct carries a `network_tokens` field NDJSON's doesn't. Every fact therefore **flattens to shared scalars before unioning** — no whole struct is ever passed through a union. Surrogate keys are `concat('<source>_', event_id)` so the two sources can't collide.

**Some metrics should not exist.** `resolution_minutes` (real elapsed time) exists only for NDJSON. `sla_target_minutes` / `sla_breached` (target and breach flag) exist only for multiline. There is no valid conversion between them. So there is no blended "support performance" metric in this warehouse — there are two, `metric_support_resolution_time` and `metric_support_sla_breach_rate_multiline`, and the naming makes the scope unavoidable. Same for FX: `amount_minor_usd` and `fx_rate_quote_per_usd` are multiline-only and NULL for NDJSON, and the only USD-total metric is explicitly named `metric_transaction_volume_usd_multiline`.

**A coincidentally-similar field is not a foreign key.** `fct_refunds.original_transaction_id` and `fct_support_tickets.related_transaction_id` look exactly like FKs to `fct_transactions.transaction_id`. They are independently-generated random UUIDs in both source generators. Joining on them produces a technically-valid query returning a nearly-empty result set that looks like a real finding. So `metric_refund_rate` is built from two independently-aggregated CTEs joined on `(event_date, source)` — a `FULL OUTER JOIN` on grain, never a join on the UUID.

**Every rate is computed from raw counts at a declared grain, never averaged from another rate column.** All 9 metric models follow this. It matters for a reason I'll get to in the next part, which is that it's a Simpson's-paradox trap with a real number attached.

Two corrections came out of the pre-implementation review, both concrete and falsifiable rather than stylistic: a factual error about a prior tag's status, and a false assertion that `fx_rate_quote_per_usd` would be non-null for all multiline rows — it's specifically NULL for the 276 USD-and-`"US$"` multiline rows, because the FX table's own base currency never gets a rate row. Both caught before any code was written.

One more thing verified rather than assumed: money is not uniformly minor-unit here. Only `transaction.*` has the v1-major-float vs. v2-minor-int drift. `refund.amount` and `payout.gross_amount` are plain major-unit floats in *both* schema versions. Checked against the generators.

---

**Next up — [Part 4: Serving and CI/CD](LINK-PART-4).** Designing guardrails against a text-to-SQL model that's better at SQL than the guardrail, the 0.7-point gap that is the exact shape of every Simpson's-paradox reporting bug, and the phase where I built the wrong thing and then deleted it.

*Part 3 of 8. Start at [Part 1](LINK-PART-1) · Full repo: [GitHub](LINK-REPO)*
