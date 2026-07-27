# ADR-0011: GB-scale synthetic data regeneration architecture

**Status:** Accepted
**Date:** 2026-07-27
**Related:** [ADR-0008](0008-novalake-terminus-and-cerberus-succession.md), [ADR-0010](0010-v0.7-silver-not-gold-comparison-target.md)

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
- The final full-scale event count is not fixed by this ADR — it's set by
  the pilot's measured cost, within the 25M upper bound justified above. A
  materially lower number than 25M is an anticipated, acceptable outcome,
  not a failure to hit target.
- Deliberate skew injection is a new, additive generator behavior with no
  precedent in this codebase before now — recorded here rather than treated
  as an incidental side effect of "preserving existing ratios," since it
  isn't preserving anything, it's adding something new for a specific,
  named `v0.9` purpose.

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
