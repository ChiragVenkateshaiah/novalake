# ADR-0011: GB-scale synthetic data regeneration architecture

**Status:** Accepted
**Date:** 2026-07-27
**Amended:** 2026-07-28 (pilot results; table-quota constraint + §8 in-place rule)
**Related:** [ADR-0008](0008-novalake-terminus-and-cerberus-succession.md), [ADR-0009](0009-agentic-integration-mcp-gated-review-then-act.md), [ADR-0010](0010-v0.7-silver-not-gold-comparison-target.md)

## Context

ADR-0008 pinned a prerequisite for `v0.9` (Spark optimization): regenerate the
synthetic payments data at GB scale (tens of millions of events) before any
optimization work starts — the current datasets (~7,105 ndjson rows / ~5 MB;
~4,100 multiline events across 9 pages / ~7.7 MB) are "noise, not
engineering" for query-plan/liquid-clustering/`OPTIMIZE` work. ADR-0008 named
the prerequisite but didn't design it. This ADR is that design, per this
project's convention that a genuine architectural decision gets its own ADR
rather than a `checkpoint.md` note (the corrected lesson from ADR-0010, where
a scope deviation was nearly recorded in the wrong place).

Both current generators (`data/generators/generate_events.py`,
`generate_multiline.py`) build their entire output in one in-memory Python
structure before writing — a flat list for ndjson, a single pretty-printed
JSON array of "pages" for multiline. Neither scales to tens of millions of
events as written: the ndjson generator's peak memory grows linearly with
row count, and the multiline generator's single-`json.dump` structure is
independently incompatible with Spark's `multiLine=true` reader, which loads
a whole file as one task regardless of memory — a giant single-file multiline
document would be a hard ceiling on ingest, not just a memory problem during
generation.

Both generators encode specific, deliberate defect-injection logic (10
event-type weights, `schema_version` 1.0/2.0 drift, ~3% malformed risk
field, 3 sentinel timestamp values, ~1.5% replay-duplicate event_ids,
dirty-currency/country-alias injection, and — on the multiline side —
record-count-reconciliation mismatches, dead-letter `partial_failures`, and
cross-page merchant-dimension drift) that every downstream Bronze/Silver/
Gold/`v0.6`-GenAI/`v0.7`-DLT transformation and dbt test was built and
validated against. A regeneration that changes these ratios changes what
"correct" downstream output even means — this is not a generic synthetic-
data-at-scale problem, it's "reproduce this exact generator's exact defect
catalog at ~1,000–4,000x the row count."

## Decision

**Target scale, revised after the pilot — see "Pilot results" below: ~5,000,000
events, not the original 25,000,000 working estimate.** The original plan was
25,000,000 events as an upper bound to test toward, not a firm commitment —
split proportionally to the current 63.4%/36.6% ndjson/multiline event ratio
(16M ndjson / 9M multiline, ~25.4M once the ~1.5% duplicate-injection
addition is counted). A small pilot batch (~1M events, same split) was
generated and validated end-to-end first, exactly as planned; the pilot's
real cost-per-GB and cost-per-table-rebuild numbers are what set the final
full-scale target below — landing materially lower than 25M (an explicitly
acceptable outcome per the original plan) because Free Edition's daily
compute quota — already observed to exhaust mid-session once on `v0.7` —
doesn't comfortably support 25M once the `v0.9`
medallion-rebuild cost (103 dbt models flipping from view to table
materialization) is counted.

**Pilot results (2026-07-27, gated run under ADR-0009)**: ~1.01M events
(649,600 ndjson + 364,679 multiline, matching the ~640K/~360K targets plus
expected duplicate-injection growth) ran end to end — generation, Bronze
ingest, `dbt run`/`dbt test` at `is_gb_scale=true` — in ~8 minutes,
`TERMINATED SUCCESS`. Correctness confirmed precisely, not approximately:
`silver_gb.int_events_deduped` landed at exactly 640,000 rows (649,600 minus
the exact 9,600 injected duplicates), confirming the chunked
duplicate-injection tie-break fix (§2, `ingested_at + 1s`) resolves
deterministically; `silver_gb.int_multiline_merchants` landed at exactly 100
(the distinct merchant count) across 800 pages / 40 files, empirically
confirming the "zero SQL changes" cross-page-resolution claim (§3) rather
than just reasoning about it; defect ratios matched target almost exactly
(sentinel timestamps 5.02% vs. 5% target, malformed risk field 2.98% vs. 3%
target); measured bytes/event (~711 B ndjson, ~1,890 B multiline) landed
within 1% of this ADR's original extrapolation. One live, expected finding:
`bronze_gb` does not auto-create the way a DLT pipeline's declared schema
does — a plain PySpark `saveAsTable()` requires the schema to already exist
— fixed with a gated `CREATE SCHEMA IF NOT EXISTS novalake.bronze_gb` before
the successful rerun.

Extrapolating the pilot's ~8-minute runtime linearly to the original 25M
target implied **~3.3 hours** for generation+ingest+dbt alone, before any of
`v0.9`'s optimization experiments (each wanting its own further `dbt run`).
Presented to Chirag as a real risk on two fronts — the daily compute quota,
and Databricks job timeout ceilings (never checked against a run this long)
— he chose **~5,000,000 events** (~40 minutes extrapolated) over ~10M or
holding at 25M: enough scale to be genuinely multi-GB and produce real
query-plan/file-layout characteristics (the actual point of this
prerequisite), comfortably inside both the timeout and quota risk envelope.

**Schema/landing layout**: UC schemas `novalake.bronze_gb`, `silver_gb`,
`gold_gb` (matches `v0.7`'s `_dlt`-suffix precedent) — existing `bronze`/
`silver`/`gold` tables and every row count already pinned across `docs/01-08`
and several ADRs stay untouched and accurate as historical record. Raw files
land in a new subfolder inside the *existing* landing volume
(`/Volumes/novalake/bronze/landing/gb_scale/{ndjson,multiline}/`), not a new
UC Volume object.

**Generator rewrite approach**: both scripts rewritten in place (not new
sibling scripts) to stream-write in Python, bounded-memory chunks, with a new
`argparse` CLI (row/event count, seed, chunk size, output directory) —
staying pure stdlib, not a PySpark/Faker rewrite, to keep the exact
defect-injection logic and its call-site control over probabilities intact
with the lowest risk of silently changing behavior.

**ndjson (`generate_events.py`)**: generate and write in bounded chunks
(default 250,000 events/chunk) instead of one in-memory list. Duplicate-event
injection moves from a single post-hoc pass over the full dataset to a
per-chunk pass (same ~1.5% global ratio, same mechanism — copy an
already-generated event, stamp a new `ingested_at`) — with one explicit fix:
duplicates are stamped with `ingested_at + 1s`, not real elapsed wall-clock
time, so `int_events_deduped.sql`'s ordering (`try_cast(ingested_at as
timestamp) desc, _ingested_at desc`) still resolves deterministically even
though the chunked pass collapses the original's multi-second generation gap
to near-zero. Shuffle also moves to per-chunk (physical row order isn't a
preserved property; nothing downstream depends on it). A new, additive
`--skew-merchant-ids` parameter (default off) lets a small subset of
`merchant_id`s (e.g. 2 of the 100 `mer_10NN` values) receive a
disproportionate share of transactions — necessary because ADR-0008 names
"skew handling" as an in-scope `v0.9` optimization technique and the current
generator draws merchant IDs uniformly (checked directly — no hot key exists
anywhere today). This ships with the generator rewrite because it's a
generation-time parameter, not something that can be added after the
expensive full-scale run already happened without it.

**Caveat, stated not hidden**: because chunking changes the sequence of
`random.*()` calls, rerunning the unflagged script (`N=7000, seed=42`) will
not reproduce the currently-landed dataset byte-for-byte, even with identical
distributions. Harmless — the existing landed dataset is never regenerated,
and raw JSON payloads are never committed to git (`CONTRIBUTING.md`'s
raw-data policy) — only the generator script and data dictionary are
version-controlled.

**multiline (`generate_multiline.py`) — the real design surface**: replaces
the single `json.dump(pages, indent=2)` call with many part-files, each a
syntactically complete, independently `multiLine=true`-readable JSON array
of `--pages-per-file` pages (default 200 for the full run). **Page numbering
stays global and monotonic across the entire run, independent of which file
a page lands in** — this is the one detail that lets
`src/dbt/models/intermediate/int_multiline_merchants.sql`'s cross-page
dimension resolution (`row_number() over (partition by merchant_id order by
as_of_page desc)`) keep working with **zero SQL changes**: that logic only
needs `as_of_page` to be a globally comparable ordering signal, not that all
pages live in one file — it already operates on the union of every page read
from Bronze, regardless of file count. Verified by reading the SQL directly,
not just reasoned about. `pagination.total_pages`/`has_more`/`next_cursor`
are computed against the run's true total page count, not per-file. Bronze
ingest's multiline path changes from reading one literal filename to reading
a directory of part-files (`spark.read.option("multiLine","true").json(dir)`)
— standard Spark multi-file JSON read behavior, not yet exercised in this
repo (`v0.7`'s DLT ingest read one literal file), verified live in the
pilot before the full run.

**Medallion rebuild**: a single new dbt var, `is_gb_scale` (default `false`),
threaded through `generate_schema_name.sql` (schema suffix), `_sources.yml`
(source schema), and `dbt_project.yml` (materialization flips view→table)
lets all 103 existing dbt models run completely unmodified against the new
scale — not forked per-model. Documented in full in the `v0.9` implementation
plan (`docs/09-spark-optimization.md` once written), not repeated here since
it's a mechanism, not an architectural decision on its own.

**Table-quota constraint, discovered post-pilot (2026-07-27 evening
warning, confirmed 2026-07-28) — updated in place, same as the pilot results
above**: a live Databricks warning during the pilot flagged Unity Catalog
approaching a per-schema table quota. Checked exactly, not just from the
warning's "80%" framing, via the Resource Quotas API
(`GET /api/2.1/unity-catalog/resource-quotas/schema/{schema}/table-quota`,
read-only, ungated per ADR-0009):

```
novalake.silver_gb : quota_count=81, quota_limit=100
novalake.gold_gb   : quota_count=20, quota_limit=100
novalake.bronze_gb : quota_count=2,  quota_limit=100
```

**This is a genuine Free Edition-specific override, not the general Unity
Catalog default.** Checked directly against Databricks' own published
resource-limits table (`docs.databricks.com`/`learn.microsoft.com` — Azure
and AWS docs agree): the standard quota is **10,000 tables/schema**,
`Fixed: No` (requestable via an account team). Free Edition's own limitations
page never states a lower number — this 100/schema ceiling is silently
enforced, not documented publicly anywhere found. **No self-service or
documented escalation path exists**: Free Edition has no account
console/account-team relationship (`getting-started/free-edition-limitations`
confirms "No access to the account console or account-level APIs") and is
explicitly outside the Databricks support policy/SLA; the one Free-Edition-
specific increase mechanism that does exist (LinkedIn identity verification)
is documented as covering only serverless GPU compute and outbound internet
access, not Unity Catalog quotas. An `help@databricks.com` request remains
technically possible (see "Alternatives considered" below) but with no SLA
for a free account. Treated here as a design constraint to build around now,
not a blocker worth waiting on — re-verify both `quota_count` *and*
`quota_limit` via the live API before relying on either number again, rather
than assuming this write-up is still current.

**Why this run stays safe**: table count tracks *model count*, not row
count. The pilot already materialized the full applicable model set (101 of
103 — `gold.genai` excluded per this ADR's own scope) at small scale — and
`silver_gb`'s 81 + `gold_gb`'s 20 sums to exactly that 101, confirming the
quota counts really do reflect the model set, not something else. The
planned ~5M-event full run re-runs `dbt run --vars "{is_gb_scale: true}"`
against those same 101 models, so it refreshes existing tables in place
rather than creating new ones. `silver_gb`'s 19 remaining tables of headroom
(gold_gb has 80) is the number that actually constrains `v0.9`'s next
phase — the six §8 optimization experiments, not the full-scale run itself.

**§8 design rule, adopted as a direct consequence of this constraint**:
reviewing the existing (already Opus-reviewed) §8 experiment design against
what each experiment's method actually specifies confirmed all five of
8.1–8.5 already operate **in place**, no retrofit needed: 8.1 (baseline) is
read-only `EXPLAIN`/Query Profile against a `SELECT`; 8.2 (liquid
clustering) is `ALTER TABLE ... CLUSTER BY` + `OPTIMIZE` on the existing
table, and the dbt `--select` rerun that later folds a win into permanent
config replaces that same table rather than adding one; 8.3 (`OPTIMIZE`/file
compaction) is `DESCRIBE DETAIL` + `OPTIMIZE`, also in place; 8.4 (join
strategy) is query-scoped SQL hints, no persistence at all; 8.5 (skew) is
`DESCRIBE DETAIL` on the already-clustered table plus a read-only notebook
query. The one gap: 8.6 (UDF elimination) described its comparison as a
"scratch query" without ruling out a persisted scratch table. Closed here:
8.6's UDF-vs-native-SQL-macro comparison runs as two timed `SELECT`s against
an existing `silver_gb` table (e.g. `int_transactions_clean`) — no
`CREATE TABLE` needed for a wall-clock/`EXPLAIN` comparison. **This needs a
forcing action to be a real comparison, not just a syntactic one**: a bare
`SELECT udf(col) FROM ...` followed by `.count()` lets Spark prune the
unused UDF output entirely, making both timings identical and the experiment
worthless — use an aggregate that actually consumes the value (e.g.
`count(distinct ...)` on the transformed column) or a `noop`-format write,
so the UDF genuinely executes on every row in both the UDF and native-SQL
runs. Standing rule for all of §8, not just 8.6: **no new physical table in
`silver_gb` or `gold_gb`** (dbt-model or ad-hoc) unless an experiment doc
names one explicitly as necessary — and if so, it is a gated action per
ADR-0009 (which already names ad-hoc `DROP TABLE`/DDL as gated, per its
`v0.7` amendment — e.g. the `events_deduped` dataset-type-conflict drop,
`docs/checkpoint.md`'s 2026-07-27 entry), dropped immediately after the
comparison completes. If a scratch table is ever genuinely unavoidable, it
goes in `gold_gb` (80 headroom) over `silver_gb` (19 headroom) — that
preference is the actual decision the executing session needs to make, not
just a fact to know. A quota check via the API above is a cheap, read-only
step to run again immediately before §8 starts, and again after any
exception scratch table is created — verify live, don't assume the numbers
above still hold once further sessions add tables elsewhere in the same
schemas.

## Consequences

- Two new generator CLIs exist (`--n-events`/`--seed`/`--chunk-size`/
  `--out-dir`/`--skew-merchant-ids` for ndjson; `--n-events`/`--seed`/
  `--pages-per-file`/`--out-dir` for multiline), with defaults reproducing
  today's approximate scale (7000/9 pages) as a working smoke test — the
  unflagged script stays runnable at small scale, not just at GB scale.
- The multiline source becomes multiple files on disk instead of one, for
  both the pilot and full-scale runs. Every consumer of that source (ingest,
  any future direct volume browsing) must expect a directory, not a single
  filename, for the `_gb` variant.
- `data/dictionaries/dataset_guide.md`/`dataset_guide_multiline.md` need a
  companion doc or amendment describing the GB-scale variant's identical
  defect catalog at the new scale and file layout, per `CLAUDE.md`'s raw-data
  policy (generator scripts and data dictionaries are version-controlled;
  raw JSON is not).
- The final full-scale event count was set by the pilot's measured cost, not
  fixed in advance by this ADR: ~5,000,000, materially below the 25M upper
  bound justified above — the anticipated, acceptable "pilot-informed lower
  number" outcome the original decision explicitly allowed for, not a miss
  against target.
- Deliberate skew injection is a new, additive generator behavior with no
  precedent in this codebase before now — recorded here rather than treated
  as an incidental side effect of "preserving existing ratios," since it
  isn't preserving anything, it's adding something new for a specific,
  named `v0.9` purpose.
- `silver_gb`'s narrow headroom (19 tables, at the 2026-07-28 reading, against
  the 100/schema Free Edition quota) is a standing constraint on every
  future `v0.9` session, not just a one-time check — §8's in-place-only rule
  above and the before-and-after quota-check step apply to every experiment,
  including ones not yet designed in detail (8.6's follow-on work, any
  future ADR-0012 content). Re-read live each time; don't treat 19 as fixed.

## Alternatives considered

- **Rewrite the generators in PySpark (+ Faker), using this project's own
  `databricks-synthetic-data-gen` skill pattern.** Rejected — much higher
  scaling ceiling, but real rewrite risk: reproducing exact deterministic
  seeding and the "duplicate an existing row" replay-defect trick in a
  distributed context is meaningfully harder than in a sequential Python
  loop, and this project's generators aren't Faker-shaped (custom
  weighted-distribution and deliberate-defect-injection logic, not
  realistic-name generation). Confirmed with Chirag directly before
  planning began.
- **Replace the existing small dataset in place rather than landing GB-scale
  data in parallel schemas.** Rejected — would invalidate every row count
  already pinned across `docs/01-08`, several ADRs, and `checkpoint.md`,
  requiring a large rewrite of already-shipped, tagged documentation for no
  benefit; the parallel-schema pattern already proven at `v0.7` avoids this
  entirely.
- **Scale ndjson only, defer multiline.** Rejected — multiline's own
  optimization surface (cross-file reads, larger per-page nesting, the
  reconciliation/DLQ patterns) is part of what `v0.9`'s techniques should be
  exercised against; deferring it would narrow the phase's real content for
  a rewrite-effort savings that turned out to be manageable once the
  multi-file design was worked out.
- **Pin the full-scale target at exactly 25M regardless of pilot results.**
  Rejected — Free Edition's daily compute quota is a real, already-observed
  constraint (`v0.7`'s Experiment 2 was blocked by it), and the `v0.9`
  medallion rebuild's own cost (103 models, not the ~80 originally estimated,
  flipping to table materialization) compounds it. Treating 25M as an upper
  bound to test toward, with a pilot-informed lower number as an accepted
  outcome, is more honest than committing to a number this ADR can't
  actually guarantee is affordable.
- **Request a Unity Catalog table-quota increase from Databricks for
  `silver_gb`/`gold_gb` rather than designing §8 around the existing
  100/schema cap.** Rejected — checked directly, not assumed: Free Edition
  has no account console/account-team relationship and is explicitly
  outside Databricks' support policy/SLA (`getting-started/free-edition-limitations`);
  the one documented Free-Edition quota-increase path (LinkedIn identity
  verification) is scoped to GPU compute and outbound internet, not Unity
  Catalog quotas. An `help@databricks.com` request is possible but carries
  no SLA for a free account. Designing §8 to stay in-place (see the
  table-quota constraint subsection above) is a real fix available today,
  versus an uncertain-outcome request with no committed timeline.
- **Copy tables into a scratch/comparison schema for each §8 experiment's
  before/after measurement, keeping `silver_gb`/`gold_gb` themselves
  untouched during experimentation.** Rejected — not because it would
  consume `silver_gb`/`gold_gb` table-quota headroom (the quota is
  per-schema, so a dedicated scratch schema would get its own fresh 100 and
  cost this specific budget nothing), but for two other reasons that hold
  regardless: the already-Opus-reviewed §8 methodology already gets a valid
  before/after by measuring the same table sequentially (`DESCRIBE
  DETAIL`/`EXPLAIN` before → `ALTER`/`OPTIMIZE` → measure again), so copies
  add no measurement value; and copying tables that are multi-GB at this
  scale would burn real time against Free Edition's daily *compute* quota —
  the actually-binding constraint this project has already hit once
  (`v0.7`'s Experiment 2) — for no benefit, plus a new UC schema is itself a
  gated object (per ADR-0009) needing its own creation and cleanup.
