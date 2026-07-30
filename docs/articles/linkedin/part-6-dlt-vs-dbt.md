I triggered a 150-row data-quality violation on purpose, then went looking for the rows.

The event log said this, and only this:

{"passed_records": 3042, "failed_records": 150}

An aggregate count. No row-level content anywhere queryable. The 150 rows are genuinely gone.

Part 6 of the NovaLake build log is a head-to-head: Lakeflow Declarative Pipelines (DLT) vs dbt, re-implementing the same Silver slice in both, into parallel schemas, never overwriting.

DLT's headline data-quality primitive is `EXPECT ... ON VIOLATION DROP ROW`. It reads like a cleaner replacement for the boring two-model `_clean` / `_dlq` WHERE split I'd built in dbt.

It isn't. It's a filter with telemetry, not a dead-letter queue.

That's a real, empirically-confirmed architectural difference — and the kind of thing you only learn by triggering the violation on purpose rather than reading the docs.

Three more findings that no amount of documentation reading had predicted:

→ Auto Loader rejects a literal file path. The fix is one character of glob syntax — `payments_events[.]json` — functionally an exact match on the same filename, but syntactically a glob, so it resolves as "directory with a filter."

→ DLT rejects ROW_NUMBER() on a streaming table, even though the dedup pattern in the tooling's own documented example uses it. A real conflict between the tool's example and the general Structured Streaming rule, resolved in favour of the general rule.

→ A dataset's type is immutable once registered, even if it's empty. Redeploying a STREAMING_TABLE as a MATERIALIZED_VIEW failed — despite the first attempt never having written a single row.

Parity, once it built, was exact across all five layers, plus 0 mismatched rows on an 11-column business-rule assertion.

Two more honest notes. `EXPECT` operates on scalar per-row predicates, so it cannot express row-uniqueness across a table — dbt's `unique` + `not_null` test *is* my dedup-correctness proof, and DLT has no equivalent. I substituted a weaker proxy and labelled it as weaker.

The second half of Part 6 is getting to GB scale, which meant rewriting both generators at ~1,000x the row count without losing a single one of their deliberate defects — the injected schema drift, the 3% malformed structs, the sentinel timestamps, the replay duplicates.

And an undocumented quota. Databricks' published limit is 10,000 tables per schema. I queried the Resource Quotas API directly and found 100. A genuine Free Edition override, silently enforced, stated nowhere I could find — with no escalation path, because Free Edition has no account console.

Part 6 of 8 → LINK-PART-6

#Databricks #dbt #DeltaLiveTables #DataEngineering #ApacheSpark
