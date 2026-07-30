47% vs 47.7%.

That 0.7-point gap is the exact shape of every Simpson's-paradox reporting bug: the wrong number is close enough to the right one that nobody questions it.

Part 4 of the NovaLake build log is about serving curated data to a text-to-SQL model — and the design problem that creates.

A capable text-to-SQL model will find and use a technically-valid join that a human analyst would never think to try. So the guardrails aren't for the analyst. They're for the model.

I wrote 7 numbered instructions for the Genie space. Four are adversarial. One of them I stopped trusting entirely.

Instruction #3 said: never join these two tables on `original_transaction_id` / `related_transaction_id`.

But a prose instruction saying "don't join on this column" is a *suggestion* to a model that can see the column, notices it's named `original_transaction_id`, and correctly infers what that name usually means. Those columns are independently-generated random UUIDs, not foreign keys. The join returns a nearly-empty result set that looks like a real finding.

So both columns were structurally excluded from the space's column visibility entirely — by hand in the workspace UI, because it wasn't achievable through the config the API exposes.

That's the one guardrail curation has to carry, not instruction.

Then I live-tested the Simpson's-paradox one. Asked "what's overall support ticket performance" — a coarser grain than the metric table's. It correctly kept the two sources as separate answers AND reported 47%, the count-weighted recomputation from underlying counts. The naive unweighted mean of the per-priority rates is 47.7%.

Two dashboard bugs in the same phase were invisible to reading the SQL:

→ A KPI filtered on `year(current_date())`. The wall clock moved into Q3; the data ends in June. The tile rendered null. The SQL is correct — it's anchored to the wall clock instead of `max(date_day)`.

→ A chart silently summed p50/p90 percentiles across a dimension. Counts are additive. Percentiles are not. Nothing in the SELECT is wrong; the bug lives in the chart's aggregation config.

Reviewing a query validates it in isolation. Building the artifact validates it in its runtime context. Different bug classes, neither substitutes for the other.

The CI half has the most humbling finding in the project: my deploy pipeline had been silently failing for three merges. The workspace only stayed correct because every real deploy in that stretch happened to be run manually, by me.

A broken automation that nothing depends on looks exactly like a working one.

Check that your automation is still running, not just that it's still configured.

Part 4 of 8 → LINK-PART-4

#Databricks #DataEngineering #CICD #Analytics #TextToSQL
