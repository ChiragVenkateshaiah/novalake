<!--
MEDIUM METADATA — Part 8 of 8
Title:      The one that didn't resolve
Subtitle:   Clustering quality 0.0, three remediation attempts that didn't unstick it, and why the failures are the deliverable. (119 chars)
Cover:      ../poster/part-8-what-i-take.png
SEO title:  The one that didn't resolve, and what I'd take from it (52)
SEO desc:   A skew experiment reported inconclusive rather than dressed up, a UDF that made Photon decline every downstream stage, and the series scorecard. (144)
Tags:       Apache Spark, Databricks, Data Engineering, Artificial Intelligence, Career Advice
Source:     docs/articles/novalake-full-story.md — lines 507-566, verbatim
-->

# The one that didn't resolve

### Skew handling reported as genuinely open, a Python UDF that made Photon decline every downstream stage, the scorecard for all six experiments — and what I'd actually take from nine tagged releases

*Part 8 of 8 in **The platform is the only source of truth**, a build log of a Databricks lakehouse taken end to end on Free Edition.*
*← Previous: [Four experiments that produced numbers](LINK-PART-7) · Series start: [Part 1](LINK-PART-1)*

---

**Where we are.** [Part 7](LINK-PART-7) covered experiments 8.1 through 8.4 — baseline, liquid clustering (including an 86% "improvement" that turned out to be a cache artifact), compaction, and join strategy. Two experiments remain. Neither produced a clean win, and that's most of why they're worth writing up.

---

## Six experiments, five results, one open question (continued)

**8.5 — Skew handling, reported as unresolved.** This needed real skew, which this codebase didn't have — checked directly, both generators drew merchant IDs uniformly. So skew injection became a permanent, default-off generator parameter (`--skew-merchant-ids`), labeled everywhere as a deliberately constructed pedagogical artifact, never implied organic. Two of 100 merchant IDs get disproportionate share: **~60% combined draw share**, confirmed live on the NDJSON side at full scale. (The multiline generator carries the identical flag and ran with it, but its resulting draw share was never separately measured — so I don't claim it.)

Scratch copy preserving the real skew, force-fragmented to 8 files, then `CLUSTER BY (merchant_id)` + `OPTIMIZE`. A real rewrite happened: `numFilesAdded: 2, numFilesRemoved: 8`. And:

**`approxClusteringQuality: 0.0`.**

Against 8.2b's clean 0.784 on non-skewed data. I didn't trust the number — I queried `_metadata.file_path` grouped by `merchant_id` to check at the row level. `mer_1000` was split **321,118 / 320,443** across the two resulting files. Essentially 50/50. And every cold merchant ID I checked showed the same pattern. **Zero keys achieved separation — hot or cold.** That the *cold* keys also failed to separate is more surprising than the hot ones failing, and it's the part I still can't fully explain.

Three follow-up attempts, all of which I actually ran rather than reasoned about: a second plain `OPTIMIZE` (`numFilesAdded: 0`); a smaller `delta.targetFileSize` with the table re-fragmented to 11 files (still `numFilesAdded: 0`, despite `numIdealFiles: 6` in its own metrics); `OPTIMIZE ... FULL` (still declined). Every attempt reported `isNewMetadataCreated: false`, which is an unchased lead.

I stopped there and **reported it as inconclusive.** Not "skew degrades clustering quality, as expected" — which would have been a plausible-sounding sentence covering a result I hadn't actually explained. The finding is: under deliberate skew, clustering by the skewed key produced measured quality 0.0 with confirmed zero key separation, and three standard remediation attempts didn't unstick it. That's genuinely open.

**8.6 — UDF elimination.** A repo-wide grep found **zero UDFs anywhere in the project** — every transformation up to this point used native SQL macros. So this one was constructed too: a Python UDF mirroring the exact logic of the project's highest-complexity macro (a 4-branch `CASE` with an else), run against `silver_gb.int_transactions_clean.country_raw` (**1,367,811 rows**).

Two methodology requirements, both flagged before running. It had to execute on a real serverless PySpark job rather than the SQL warehouse — a SQL-warehouse Python UDF has different execution semantics and would never surface the plan node this experiment exists to observe. And it had to use an aggregate that genuinely *consumes* the transformed value (`count(distinct ...)`), because a bare `.count()` lets Spark prune the unused UDF output and makes both timings meaningless.

Correctness confirmed first: both variants return n=7 distinct clean country codes, matching the generator's pool exactly. Only then did I look at timing.

The plan finding was bigger than expected. The UDF plan shows a genuine `BatchEvalPython` node — and **Photon declines not just that node but every downstream stage.** The `HashAggregate`, the `Exchange` — the entire rest of the query falls back to classic Spark. The native SQL plan stayed fully Photon-native end to end.

| Variant | 1st run | 2nd run |
|---|---|---|
| Python UDF | 17.190 s | 2.105 s |
| Native Spark SQL | 1.081 s | 0.806 s |

**~2.6x slower warm-to-warm.** And the UDF's own cold-start gap — ~15 seconds, roughly 8x — is far larger than any other warm-up gap measured anywhere in this phase, where everything else showed gaps of a few seconds at most. That points at a distinct cost category: Python worker process startup for `BatchEvalPython`, not generic warehouse warming.

The caveat that belongs with those numbers: this is a **row-at-a-time Python UDF specifically**, deliberately chosen as the classic worst case. It is not a claim about vectorized pandas/Arrow UDFs, which were never built or measured here.

**The scorecard: three clear results with causal explanations (compaction, join strategy, UDF elimination), one clean win once past a threshold (clustering), one null result honestly labeled as a cache artifact rather than a win, and one genuinely unresolved open question (skew).** An honest mix. If all six had been wins, you should trust the writeup less, not more.

---

## What I'd actually take from this

**Specificity is the whole game.** Every genuinely useful finding in this project has an exact number, an exact error message, or an exact plan node attached — `nodeMinNumFilesToCompact: 4` against `totalConsideredFiles: 2`; `approxClusteringQuality: 0.0` confirmed by a per-file row split of 321,118/320,443; `{"passed_records": 3042, "failed_records": 150}` and nothing else in the event log; `NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`; exit code 127. The findings I *couldn't* pin to a number are the ones I labeled inconclusive.

**Working with an AI agent well meant building the gates before I needed them.** The four-stage escalation wasn't caution theater — each stage's boundary got tested. The AI review that suggested `.cache()` was applying a genuinely sound general principle to a runtime it didn't know the constraints of, which is exactly what a smart human reviewer would have done. The gate that caught it wasn't a better argument, it was an actual execution. And the gate that made the *process* trustworthy was the log: every side-effecting action written down, dated, with parameters and outcome, because live workspace actions leave no git history and an unlogged one leaves no trace at all.

**The failures are the deliverable.** An agent that leaked its own system prompt to the most obvious probe there is. A CI pipeline that had been silently failing for three merges while looking configured and fine. A generator that duplicated 122,592 rows because nobody cleared stale part-files. A "pin the SQL" guarantee that turned out to be a strong prior. A clustering result I chased three ways and still can't explain. If I'd left those out, this would read as marketing, and every engineer who's actually shipped something would know it.

**And the throughline, now with a fourth tier the project earned:** validation catches syntax, local runs catch integration, real end-to-end runs catch what the platform actually does — and only real runs at real volume, against real adversarial input, catch the rest. That's true whether the code came from you or from your very capable, occasionally-and-confidently-wrong AI pair.

---

## Where it ends, and what's next

NovaLake is done at `v0.9`. That's a decision, recorded as an ADR, not a project that ran out of steam.

The reason is a platform boundary I verified rather than assumed. Serverless compute exposes no Spark UI, no cluster-sizing knobs, and locks most `spark.conf` settings. Query profiles and `EXPLAIN` plans *are* fully available — which is why the query-and-data-layout half of Spark optimization was in reach and got done properly. The infrastructure half — executor and shuffle tuning, cluster sizing, disk-cache strategy — is capped by the platform, not by effort. And real production semantics can't exist in a single Free Edition workspace: a same-workspace "prod" distinguished only by which identity deploys is a semantic overlay, which is why I built one and then deleted it.

Rather than fake either inside NovaLake, both succeed to a new project: **Cerberus** — AWS, Terraform-first IaC, classic/self-managed Spark compute, genuinely separate dev and prod with real promotion and reproduce-from-nothing infrastructure, with NovaPay (the companion payments app) as its upstream data producer instead of synthetic generators. The Spark mastery splits deliberately: NovaLake covered what serverless exposes; Cerberus covers what serverless hides.

Worth naming honestly: a paid Databricks workspace on classic compute *would* have exposed those missing knobs. That alternative isn't technically ruled out — it was passed over by choice, for portfolio breadth rather than technical necessity, and the ADR says so in those words.

The full repo is public — 103 dbt models, 12 ADRs, 9 phase docs following a fixed 12-section template, and a dated revisit log in `docs/checkpoint.md` of every gated AI action taken against the live workspace: tool call, parameters, outcome, unabridged. Git history itself is a mixed bag — the earliest PRs landed as merge commits, the later ones got rebased or squashed on the way in, so the raw commit graph alone doesn't reliably preserve every reverted fix. What does is that the failed runs and dead ends got written down as they happened — in the phase doc, in the ADR, in the checkpoint log — not smoothed over afterward or reconstructed from memory once the phase looked done. The debugging journey is the valuable part; if it had depended on nobody ever squashing a branch, it would already be gone.

**[GitHub repo link]**

If you build something like this, the one habit I'd steal from it isn't the architecture. It's this: when a run passes, go read what it actually did.

---

## The whole series

| Part | What it covered |
|---|---|
| [**1**](LINK-PART-1) | The collaboration model — four stages of AI access |
| [**2**](LINK-PART-2) | Bronze, and the confidently wrong fix |
| [**3**](LINK-PART-3) | Silver and Gold — two pipelines deliberately never unified |
| [**4**](LINK-PART-4) | Serving and CI/CD — guardrails, and a green check that lied |
| [**5**](LINK-PART-5) | The agent that leaked its own system prompt |
| [**6**](LINK-PART-6) | DLT versus dbt, and getting to GB scale |
| [**7**](LINK-PART-7) | Four experiments that produced numbers |
| **8** | The one that didn't resolve *(you are here)* |

*Thanks for reading all eight. If one part was useful, the one I'd point a working data engineer at is [Part 7](LINK-PART-7) — the 86% improvement caused by nothing is the most transferable mistake in the whole build.*
