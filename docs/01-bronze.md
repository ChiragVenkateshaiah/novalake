# Module 1 · Bronze — Raw Event Ingestion

`Status:` Validated  ·  `Owner:` Chirag  ·  `Last updated:` v0.1  ·  `Est. time:` ~45 min

## 1. Learning Objectives
- [x] Can explain why Bronze enforces no schema and drops nothing
- [x] Can explain the difference between syntactic corruption (`_corrupt_record`) and
      semantic/type drift across records — and why permissive mode only catches the former
- [x] Can read Spark's inferred schema and explain why a polymorphic source produces
      a wide, mostly-nullable union schema

## 2. Prerequisites
- `v0.0` complete: `novalake` catalog/schemas/volume exist, both raw files landed.

## 3. Where This Fits
```
payments_events.json  →  [this module]  →  novalake.bronze.raw_events  (7,105 rows)
```
The multiline file was **not** touched in this module — its raw capture happens at
the start of `v0.2`, since reading it (`multiLine=true`) is tightly coupled with the
explode/flatten work that follows it.

## 4. Concepts & Background
- **Schema-on-read** — structure inferred at read time, not enforced at write time;
  lets Bronze accept whatever shape arrives.
- **Permissive mode's real boundary** — `PERMISSIVE` (Spark's JSON default) only
  protects against syntactically broken JSON, surfaced via `_corrupt_record`. This
  file had zero corrupt records — every line was valid JSON. Its mess is entirely
  *semantic* (type drift across otherwise-valid records), which this mechanism
  cannot see at all.
- **Polymorphic union schema** — 10 event types sharing one envelope produced a
  `payload` struct with every type's fields as nullable siblings. Sparsity (a field
  being `null` most of the time) is normal and expected here — it is *not* evidence
  of a problem on its own.
- **Two different kinds of "collapse," with two different costs:**
  - *Struct-vs-scalar* (`payload.risk`): destructive. A 3% minority of malformed
    rows forced the 97% well-formed majority to lose its structure too — there's
    no single column type that holds both a struct and a string, so Spark fell
    back to text for the whole column.
  - *Type-vs-type* (`payload.amount_minor`, int vs string): non-destructive. A
    `cast("long")` recovers every value regardless of which shape it started as.
- **Drift that isn't "collapse" at all** — some schema differences aren't about a
  field losing structure, they're about the *same concept* being represented two
  different ways across schema versions:
  - *Key renaming*: `cust_id` (v1) vs `customer_id` (v2) — two field names, one concept.
  - *Structural reshaping*: `source_system` (v1, flat string) vs `source` (v2, a
    3-field struct) — not a renamed key, a different shape entirely.
  - *Value-level dirtiness*: `payload.currency` mixing `"USD"`/`"usd"`/`" GBP"` —
    one consistent shape (plain text), genuinely inconsistent values. Needs a
    distinct-value count, not a shape profile.

## 5. Data Contract / Schema in Scope
- Source: NDJSON, one event envelope per line, 10 polymorphic event types.
- Target: `novalake.bronze.raw_events` — Spark's inferred schema + `_source_file` +
  `_ingested_at`. No fields renamed, dropped, or retyped.
- Grain: one row per source line. ~1.5% intentional replayed `event_id`s left
  untouched on purpose — dedup is Silver's job, not Bronze's.

## 6. Step-by-Step Implementation
- 6.1 Schema discovery (infer, inspect) — ✅ done. 51 leaf fields, `payload` alone
  spans every event type's fields as nullable siblings.
- 6.2 Investigate `event_timestamp` and `payload.risk` inferred types — ✅ done.
  Both inferred as `string`.
- 6.3 Check for `_corrupt_record` — ✅ done. Column absent entirely — zero
  syntactically broken lines in the source file.
- 6.4 Add `_source_file` / `_ingested_at` — ✅ done.
- 6.5 Write to `novalake.bronze.raw_events` — ✅ done. Row count verified against
  the per-(event_type, schema_version) breakdown: sums to exactly 7,105.
- 6.6 Build a reusable schema-drift audit tool
  (`notebooks/01_bronze/02_schema_drift_audit.py`) — ✅ done. Classifies every
  string-typed leaf field by value shape (`json_object`, `json_array`, `numeric`,
  `date_like`, `plain_text`, `null`) and flags any field with more than one
  non-null shape, without needing to already know where to look.
- 6.7 Fix a case-sensitivity bug in the audit's null-filter (`"Null" != "null"`)
  that was producing 46 false positives — ✅ done. Confirmed against the
  generator's own known counts.
- 6.8 Manually catalog the drift categories the audit *can't* see (type-equivalent
  collapse, key renaming, structural reshaping, value dirtiness) — ✅ done, see §4.

## 7. Operational Considerations
- Write mode is `overwrite` for this static, one-time batch load — safe to re-run,
  fully replaces the table from the current source file each time. Will change to
  an incremental/idempotent pattern (`COPY INTO` or Auto Loader) once this becomes
  a scheduled Job — noted here, not solved here.
- **Architecture pivot (2026-07-16):** this notebook's logic now also exists as
  `src/ingest.py`, a job-driven PySpark script with the identical read/transform/
  write behavior, wrapped in `resources/dbt_job.yml` as a DAB `spark_python_task`.
  See `docs/checkpoint.md`'s "Revised decision." This notebook stays in place as
  the historical, hand-run `v0.1` record — it is not deleted or superseded for
  validation purposes, just no longer the forward path for scheduled runs.
- The shape-audit tool has real, documented blind spots — see §4's "type-vs-type"
  and "drift that isn't collapse" cases. It's one tool for one category of problem,
  not a complete Bronze health check.

## 8. Data Quality & Governance
- None enforced yet — Bronze intentionally has zero validation.
- This module's real output, for governance purposes, is the **Silver scope list**:
  5 distinct problem categories needing 5 distinct fixes —
  struct collapse (`from_json` with explicit schema), type-equivalent collapse
  (`cast`), key renaming (`coalesce`/union), structural reshaping (version-branched
  parsing), value dirtiness (normalization). `v0.2` works through all five.

## 9. Validation & Acceptance Criteria
- [x] `novalake.bronze.raw_events` exists and is queryable
- [x] Row count matches source line count (7,105)
- [x] `_source_file`, `_ingested_at` populated on every row
- [x] Schema-drift audit confirms exactly 2 fields with genuine multi-shape
      collapse: `event_timestamp` (date_like: 4,521 / numeric: 2,440 / null: 144),
      `payload.risk` (json_object: 3,131 / plain_text: 103 / null: 3,871)

## 10. Key Takeaways
- Bronze ingestion was fully lossless — 7,105 rows, byte-identical to the source,
  zero transformation applied.
- `_corrupt_record` / permissive mode protects against syntax errors only. This
  dataset has none; its entire problem is semantic type drift, which is invisible
  to that mechanism and shows up instead as schema inference effects.
- Struct-vs-scalar conflicts collapse *destructively* (the well-formed majority
  loses real structure because of a malformed minority). Type-vs-type conflicts
  collapse *non-destructively* (a cast recovers everything). Worth never
  conflating these two — they need different fixes and carry different risk.
- A general-purpose shape-profiling tool can find struct collapse without already
  knowing where to look — genuinely useful, and reusable on any future Bronze
  source — but it has real, specific blind spots (type-equivalent collapse,
  cross-field semantic links like renamed keys, value-level dirtiness in an
  already-consistent field). Knowing a tool's blind spots is as important as
  knowing what it catches.
- This dataset's real Bronze→Silver handoff is 5 problem categories, not 1.
- Practical bug worth remembering: Python string comparisons are case-sensitive —
  `"Null" != "null"` silently broke a filter and produced 46 false positives
  before being caught by sanity-checking the output against known counts.

## 11. Knowledge Check
- **Q1: Why didn't `_corrupt_record` catch the `risk`-as-string records?**
  Because every record was syntactically valid JSON. `_corrupt_record` only flags
  lines that fail to parse as JSON at all. `risk` being the "wrong" *type* (a
  string instead of a struct) is a schema problem, not a syntax problem — it
  passes permissive mode silently and only shows up as a collapsed type in the
  inferred schema.
- **Q2: If you added a brand-new event type and re-ran this notebook, what would
  happen, given `mode("overwrite")`?**
  The table would be fully replaced based on whatever Spark infers fresh from the
  now-larger file — safe and correct for a one-time full reload, but not how a
  real recurring ingestion job should behave. A production version would need
  incremental, idempotent loading (`COPY INTO` or Auto Loader) instead of a full
  overwrite each run — deferred to `v0.5`, when this becomes a scheduled Job.

## 12. References
- Internal: `docs/checkpoint.md`, `docs/00-setup.md`,
  `notebooks/01_bronze/01_ingest_raw_events.py`,
  `notebooks/01_bronze/02_schema_drift_audit.py`
- Data dictionary: `data/dictionaries/dataset_guide.md` (cross-referenced against
  empirical findings above — all matched)

## Changelog
| Date | Change | Author |
|------|--------|--------|
| v0.1 | Module created, ingestion notebook run, table validated | Chirag + Claude |
| v0.1 | Schema-drift audit tool built, case-sensitivity bug found and fixed | Chirag + Claude |
| v0.1 | Module completed and validated | Chirag + Claude |
| 2026-07-16 | Architecture pivot: notebook logic ported to `src/ingest.py`, wrapped in a DAB job resource. Notebook kept as historical record. | Chirag + Claude |