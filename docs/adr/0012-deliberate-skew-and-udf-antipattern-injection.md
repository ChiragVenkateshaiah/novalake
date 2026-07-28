# ADR-0012: Deliberate skew injection and UDF-antipattern construction for §8's pedagogical experiments

**Status:** Accepted
**Date:** 2026-07-28
**Related:** [ADR-0008](0008-novalake-terminus-and-cerberus-succession.md), [ADR-0009](0009-agentic-integration-mcp-gated-review-then-act.md), [ADR-0011](0011-gb-scale-data-regeneration.md)

## Context

ADR-0008 named "skew handling" and "UDF elimination" as two of `v0.9`'s six
in-scope Spark optimization techniques (`docs/09-spark-optimization.md`
`§8.5`/`§8.6`). Both techniques are meaningless without something real to
actually handle or eliminate — checked directly, not assumed, before
committing to this ADR: this codebase's generators drew merchant/customer
IDs uniformly (no hot key existed anywhere before ADR-0011's rewrite), and a
repo-wide grep across `src/dbt/` found zero UDFs anywhere in the project —
every transformation up to `v0.9` used native SQL macros. Without
deliberately constructing something, `§8.5` and `§8.6` would have had no
real content to measure, and `v0.9` — NovaLake's terminus, no `v0.10` — has
no future phase to defer this to.

**Why this is its own ADR rather than folded into `docs/checkpoint.md`'s
narrative or left solely in the module doc:** per `docs/adr/README.md`'s own
stated division of labor, `checkpoint.md` carries the dated narrative for
what actually happened (and already does, in detail, for both `§8.5` and
`§8.6`); `docs/09-spark-optimization.md` carries the full technical
methodology and evidence a learner would work through. This ADR is neither
— it's the one-decision-per-file formal record that two *deliberately
constructed* artifacts (not organic findings) exist in this codebase, why,
and what happened when they were exercised, matching the same discipline
ADR-0010 and ADR-0011 already established for this project's decision
series.

## Decision

Construct both artifacts deliberately, and label them as constructed
pedagogical devices everywhere they appear in `docs/09-spark-optimization.md`
— never implied to be organic findings.

1. **Skew**: a `--skew-merchant-ids` generator parameter. ADR-0011 is the
   mechanism record for the **ndjson** generator's copy of this parameter
   specifically (`data/generators/generate_events.py`) — it does not
   document that `generate_multiline.py` carries the identical flag too;
   both generators shipped it together as part of the same rewrite, and
   this ADR is the first place that's recorded formally. 2 of 100
   `merchant_id`s (`mer_1000`, `mer_1001`) receive a disproportionate share
   of transactions. Confirmed live on the **ndjson side** at full GB scale
   (stage 1 of the staged full-scale run): **~60% combined draw share** on
   the two hot IDs (`docs/checkpoint.md`, 2026-07-28). The multiline
   generator carries the same flag and was run with `skew_merchant_ids=2`
   for the full-scale build, but its resulting draw share was never
   separately measured — not claimed here.
2. **UDF**: a Python UDF mirroring `src/dbt/macros/clean_country.sql`'s
   exact logic (the highest-complexity existing macro, a 4-branch `CASE` +
   `else`), constructed specifically for `§8.6`'s comparison. No organic UDF
   exists anywhere else in this codebase, and none should — this UDF is a
   demonstration artifact, timed against the native SQL it deliberately
   duplicates, not a transformation kept in the pipeline. Uploaded ephemerally
   to the workspace for one gated, one-time job run (`databricks jobs
   submit`, not a saved bundle resource) and deleted immediately after —
   unlike the skew knob, this artifact has no ongoing use. **This
   supersedes ADR-0011's own more specific `§8.6` prescription** ("two timed
   `SELECT`s against an existing `silver_gb` table," written when `§8.6` was
   still unbuilt) — execution instead used a serverless one-time job
   (`spark_python_task`), per `§8.0`'s compute-surface mapping: a
   SQL-warehouse Python UDF has different execution semantics and would
   never surface the `BatchEvalPython` plan node this experiment exists to
   observe.

## Results observed (`§8.5`, `§8.6`)

Full technical narrative, methodology, and evidence live in
`docs/09-spark-optimization.md`; summarized here as the results this ADR
exists to record.

**Skew handling (`§8.5`):** run on a **disposable scratch copy** of
`gold_gb.fct_transactions` (`gold_gb._scratch_fct_transactions_skew_test`),
not the real table directly — the real table's own `§8.2` clustering was
already confirmed a no-op (2 files, below the compaction threshold), so the
scratch copy was force-fragmented to 8 files (`INSERT OVERWRITE ...
REPARTITION(8)`, row count confirmed unchanged) before clustering, the same
recipe `§8.2b` used, per ADR-0011's own named scratch-table exception
(gated, dropped immediately after). Clustering this real-skew data by
`merchant_id` produced `approxClusteringQuality: 0.0` — a real, quantified
clustering failure, confirmed at the row level (querying
`_metadata.file_path` showed every merchant ID, hot and cold alike, split
almost evenly across both resulting files — zero keys achieved separation).
The same clustering pass also compacted the scratch copy from 8 files down
to 2, below the 4-file compaction threshold `§8.2b` established, and three
follow-up attempts to force further improvement (a second `OPTIMIZE`, a
much smaller target file size with more files available, `OPTIMIZE ...
FULL`) all declined to rewrite anything. Reported honestly as a genuinely
unresolved open question — this project's discipline treats "we could not
fully explain this" as a valid, reportable outcome, not a result to
suppress or paper over with a fabricated explanation. The scratch table was
dropped immediately after use, per the same discipline.

**UDF elimination (`§8.6`):** the constructed UDF and the native SQL macro
it mirrors return identical results (`n=7` distinct clean country codes),
confirmed before any timing was trusted. The UDF's `EXPLAIN` plan showed a
real `BatchEvalPython` node, and Photon declined not just that node but
**every downstream stage** of the same query plan — the whole rest of the
aggregation fell back to classic Spark, while the native SQL plan stayed
fully Photon-native end-to-end. Timing, each variant run twice: UDF 17.190s
(1st) / 2.105s (2nd); native SQL 1.081s (1st) / 0.806s (2nd) — the UDF is
~2.6x slower even warm-to-warm, and its cold-start gap (~15 seconds, ~8x) is
far larger than any other before/after warm-up gap measured this session,
pointing to a distinct cost (Python worker process startup) rather than
generic warehouse warming.

## Consequences

- The `--skew-merchant-ids` generator parameter is a permanent, reusable
  addition to both generators (default off) — any future regeneration at
  any scale can reproduce this same skew pattern; it is not a one-time hack
  specific to this session's run. Its ndjson-side effect is measured
  (~60% combined share); its multiline-side effect is not, and should not be
  assumed identical without checking.
- The UDF script itself was **not** kept in the repo — a pure demonstration
  artifact uploaded ephemerally for one job run and deleted immediately
  after, matching this project's scratch-artifact discipline
  (`v0.7`'s `_scratch_dlq_test`, `v0.9`'s `§8.2b`/`§8.5` scratch tables). Its
  full logic is preserved durably in `docs/09-spark-optimization.md`'s
  `§8.6` write-up instead of as a standing repo file with no ongoing use.
- `§8.5`'s clustering-quality-degradation finding stays genuinely open —
  anyone tuning liquid clustering on real, skewed production data should
  treat "the usual levers didn't unstick it" as a real finding from this
  project, not assume it was fully root-caused.
- `§8.6`'s ~2.6x/`~8x`-cold-start result reflects a **row-at-a-time Python
  UDF specifically** — the worst-case, most-classic form of the antipattern
  ADR-0008 named. It is not a claim about vectorized (pandas/Arrow) UDFs,
  which were never built or measured here; see Alternatives.
- Both `docs/09-spark-optimization.md` and this ADR now consistently label
  these two artifacts as constructed, not organic, everywhere they're
  referenced — a reader encountering either result in isolation (e.g. via
  the ADR index) still gets the correct framing.

## Alternatives considered

- **Wait for organic skew/UDF usage to emerge naturally in a future phase.**
  Not a live option actually weighed during this work — ADR-0008 fixed
  `v0.9` as NovaLake's terminus (no `v0.10`) before this phase's experiments
  were even planned, foreclosing this alternative in advance. Listed here
  for completeness, not as a real choice made in the moment.
- **Use the multiline source's already-incidental skew instead of injecting
  a new one.** `§8.5`'s own "free bonus" observation measured this directly
  (240,203 raw merchant-reference rows collapsing into just 100 groups).
  Rejected as a *substitute* for the deliberate transaction-level injection
  — it's a structurally different phenomenon (repeated cross-page
  dimension references collapsing via a window function), not a hot key
  concentrating transaction volume, so it wouldn't exercise `fct_transactions`
  clustering the way ADR-0008's "skew handling" scope intends.
- **Inject skew at query time** (e.g., skewing a scratch copy's key
  distribution after the fact) **rather than at generation time.** Rejected
  on the same sequencing grounds ADR-0011 already established for this
  exact knob: skew has to be a generator parameter shipped before the
  expensive full-scale run, not a scratch-query trick designed after the
  data already exists.
- **Use a vectorized (pandas/Arrow) UDF instead of a row-at-a-time Python
  UDF.** Not built here — genuinely out of scope for this specific
  comparison, not rejected on the merits. `§8.6`'s row-at-a-time UDF is
  deliberately the classic, worst-case form of the antipattern ADR-0008
  names; a vectorized UDF is a materially different (and generally less
  costly) technique that this ADR makes no claim about. Its absence means
  `§8.6`'s ~2.6x/cold-start numbers should be read as "how bad the classic
  antipattern is," not "how bad every UDF necessarily is."
- **Keep the UDF script permanently in the repo** (e.g. under `src/` or a
  checked-in scratch directory) as a standing reference. Rejected — this
  project's established discipline treats one-time demonstration artifacts
  as ephemeral (created under a gated action, dropped immediately after),
  not permanent repo content; the Python logic is already fully preserved in
  `docs/09-spark-optimization.md`'s `§8.6` write-up, the actual durable
  record.
- **Present the `§8.5`/`§8.6` results without labeling them as
  constructed**, letting them read as organically-discovered production
  findings. Rejected — would misrepresent what was actually observed; this
  project's documentation discipline requires being explicit about what's
  deliberately constructed versus what's discovered, the same principle
  behind labeling `8.2b`'s scratch-copy verification as a constructed check
  rather than a production result.
