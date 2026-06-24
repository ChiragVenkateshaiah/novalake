# Dataset Guide — `payments_events_multiline.json`

**Format:** a single pretty-printed **JSON array** (the *whole file* is one JSON value).
**Read with:** `spark.read.option("multiLine", "true").json(path)`
**Scale:** 9 page documents · ~4,100 events · ~580 merchant rows · ~470 customer rows · ~7.7 MB
**Role:** raw / Bronze landing data — the **hard mode** variant of the NDJSON file.

> The whole point of this file is that `multiLine=true` returns **one row per page (9 rows)**,
> not one row per event. The real dataset lives *inside* nested arrays you have to explode,
> flatten, and join — yourself.

---

## Top-level shape (one element per page)

```
[
  {
    "export_metadata": { record_counts{map}, checksums{map}, source{…} },
    "pagination":      { page, page_size, total_pages, cursor, next_cursor, has_more },
    "reference_data":  { merchants[], customers[], fx_rates[], currency_catalog{map} },
    "data":            { events[ … ], partial_failures[ … ] },
    "audit":           { warnings[], lineage[] }
  },
  … 8 more pages …
]
```

The event `payload` is polymorphic by `event_type` (transaction / support / review /
auth / kyc / refund / payout / risk), each with its own nested shape.

---

## Embedded challenges *(what to expect — not how to solve)*

**Structural (the multiline-specific part):**
1. **One row per page.** After `multiLine` read you have 9 rows. Your first transform is
   `explode(data.events)` — and separately `data.partial_failures`, `reference_data.merchants`,
   `reference_data.customers`, `reference_data.fx_rates` — all siblings off the same row.
2. **3–4 levels of nesting.** e.g. `payload.transaction.line_items[].discounts[]` and
   `payload.transaction.payment_method.network_tokens[]`.
3. **Arrays within array elements.** `messages[].attachments[]`, `documents[].pages[]`,
   `line_breakdown[].sub_items[]`, `signals[].sub_signals[]` — nested explodes.
4. **Array-of-arrays.** `payload.transaction.risk.signal_matrix` is a list of lists.
5. **Dynamic-key maps (schema-explosion trap).** `metadata`, `balances`,
   `currency_catalog`, `checksums`, `customers[].consents`, `merchants[].tax_ids`,
   `device.sensors`. Inferred as structs they explode into sparse columns — handle them
   as maps / `from_json` with an explicit schema instead.

**Referential / cross-page:**
6. **Embedded dimensions to join.** Enrich events against `reference_data.merchants` and
   `customers` — but those arrays live per page and must be unioned first.
7. **Cross-page drift.** ~99 `merchant_id`s appear on multiple pages with a changed
   name casing or category (`as_of_page` tells you the order) — latest-wins / SCD decision.
8. **fx_rates to apply.** Normalising `currency` to a base needs the embedded `fx_rates`
   (each has an `as_of`).
9. **Counts that lie.** `export_metadata.record_counts.events` is intentionally off from
   the real array length (and some counts are `null`) — a reconciliation check.

**Record-level (carried over from the NDJSON variant):**
10. **Dead-letter records.** `partial_failures[].raw` is an **escaped JSON string** of a
    broken event — a `from_json` / DLQ-routing exercise, kept out of the clean path.
11. **Schema drift v1/v2** — `event_timestamp` epoch-millis(int) vs ISO(str) vs null;
    `cust_id`→`customer_id`; `amount` float vs `amount_minor` int/string; `source_system`
    vs `source`.
12. **Dirty values & malformed nesting** — mixed currency/country casing, ~3% of `risk`
    delivered as a string, out-of-range timestamps, replayed `event_id`s, empty/null/missing
    arrays.

---

## Suggested order of attack (Silver)
Read multiLine → explode `data.events` → flatten the `payload.<type>` structs per event_type
→ second-level explodes for nested arrays → parse dynamic maps with explicit schemas →
union + dedupe the per-page dimensions, resolve drift → apply `fx_rates` → route
`partial_failures` to a quarantine table → reconcile against `record_counts`.
