# Dataset Guide — `payments_events.json`

**Format:** newline-delimited JSON (one event object per line) · **~7,100 records** · **~5 MB**
**Domain:** NovaPay-style digital payments platform event stream
**Role in project:** this is your **raw / Bronze landing data**.

---

## The envelope (common to every event)

| Field | Notes |
|-------|-------|
| `event_id` | `evt_…` — **not unique** (replays exist, see below) |
| `event_type` | dotted type that selects the `payload` shape (polymorphic) |
| `schema_version` | `"1.0"` (legacy) or `"2.0"` — the drift driver |
| `event_timestamp` | **type varies by version** (see Challenges) |
| `ingested_at` | ISO string, set at generation time |
| `source` *or* `source_system` | **shape varies by version** |
| `payload` | event-type-specific object |

## Event types (and where the text lives)

| `event_type` | Notable nested arrays | Free text (for GenAI later) |
|--------------|----------------------|------------------------------|
| `transaction.completed` / `.failed` / `.created` | `line_items[]` | — |
| `refund.issued` | — | `reason`, `notes` |
| `payout.scheduled` | `fees[]` | — |
| `auth.session` | — | — |
| `kyc.verification` | `documents[]` | — |
| `support.ticket` | `messages[]`, `tags[]` | `subject`, `description`, `messages[].body_text` |
| `review.submitted` | — | `title`, `body` |
| `risk.alert` | `signals[]` | `notes` |

---

## Embedded challenges *(what to expect — not how to solve)*

These are intentional. Treat them as the Silver-layer exercise.

1. **Polymorphism.** `payload` schema depends entirely on `event_type`. One raw table,
   many shapes.
2. **Schema drift across versions.**
   - `event_timestamp`: v1 = epoch **milliseconds (int)**, v2 = **ISO-8601 string**,
     and a small fraction are `null`.
   - Source: v1 = `source_system` (string), v2 = `source` (struct).
   - Customer key: v1 = `cust_id`, v2 = `customer_id`.
   - Transaction money: v1 = `amount` (major-unit float), v2 = `amount_minor`
     (minor-unit int) **sometimes delivered as a string**.
   - v2-only optional field: `idempotency_key`.
3. **Nested arrays for flattening.** `line_items`, `messages`, `documents`, `signals`,
   `fees`, `tags`. Some are **empty `[]`**, some **`null`**, some **missing entirely**
   → the explode-vs-explode-outer decision is real here.
4. **Dirty categoricals.** `currency` has mixed casing / whitespace / an invalid value;
   `country` mixes `US` / `us` / `USA` / `United States` / `null`.
5. **Out-of-range timestamps.** A few epoch-zero (1970) and far-future (2099) values —
   late/early-arriving data to filter or quarantine.
6. **Replays / duplicates.** ~1.5% of `event_id`s appear more than once with a later
   `ingested_at` — dedup before Gold.
7. **Malformed nested value.** ~3% of transactions deliver `risk` as a **string**
   instead of a struct — a schema-mismatch case to catch.
8. **Numbers as strings.** Beyond `amount_minor`, watch for coercible-but-typed fields.

---

## Reading it on Databricks

- NDJSON is the default for `spark.read.json(path)` — no extra option needed.
- If you want a multiline-array variant to practise `multiLine=true`, ask and I'll
  generate one.
- Recommended first move: read everything as-is into Bronze (consider
  `rescuedDataColumn` / permissive mode) **before** trying to impose structure.
