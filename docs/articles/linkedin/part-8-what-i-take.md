I chased one result three different ways and still can't explain it.

So I published it as inconclusive, rather than writing the plausible-sounding sentence that would have covered it.

Part 8 — the last of the NovaLake build log.

The experiment: inject real skew (two of 100 merchant IDs taking ~60% combined draw share), then cluster by the skewed key.

A genuine rewrite happened. And then: `approxClusteringQuality: 0.0`. Against a clean 0.784 on non-skewed data.

I didn't trust the number, so I checked at the row level — queried `_metadata.file_path` grouped by merchant_id. The hottest key was split 321,118 / 320,443 across the two resulting files. Essentially 50/50.

And every *cold* key I checked showed the same pattern. Zero keys achieved separation — hot or cold. That the cold keys also failed is more surprising than the hot ones failing, and it's the part I still can't fully explain.

Three follow-up attempts, all actually run rather than reasoned about: a second OPTIMIZE, a smaller target file size with re-fragmentation, OPTIMIZE FULL. All declined to do anything.

The easy write-up here is "skew degrades clustering quality, as expected." That sentence sounds right and covers a result I hadn't explained.

The honest finding is narrower and more useful: under deliberate skew, clustering by the skewed key produced measured quality 0.0 with confirmed zero key separation, and three standard remediations didn't unstick it. That's genuinely open.

The scorecard: three clear results with causal explanations, one clean win past a threshold, one null result labelled as a cache artifact, and one unresolved.

An honest mix. If all six had been wins, you should trust the writeup less, not more.

What I'd take from nine tagged releases:

→ Specificity is the whole game. Every genuinely useful finding has an exact number, error message, or plan node attached. The ones I couldn't pin to a number are the ones I labelled inconclusive.

→ Working with an AI agent well meant building the gates before I needed them. The review that suggested `.cache()` was applying a sound general principle to a runtime it didn't know the constraints of — exactly what a smart human reviewer would have done. The gate that caught it wasn't a better argument. It was an actual execution.

→ The failures are the deliverable. An agent that leaked its own system prompt. A CI pipeline silently failing for three merges while looking fine. 122,592 duplicated rows from uncleaned part-files. A "pin the SQL" guarantee that was really a strong prior.

If I'd left those out, this would read as marketing, and every engineer who's actually shipped something would know it.

Validation catches syntax. Local runs catch integration. Real end-to-end runs catch what the platform actually does. And only real runs at real volume, against real adversarial input, catch the rest.

Part 8 of 8 → LINK-PART-8

#ApacheSpark #Databricks #DataEngineering #AI #EngineeringCulture
