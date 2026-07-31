<!--
LINKEDIN — Series introduction (Part 0 of 8)
Publishes:  Ahead of Part 1, paired with the Databricks Certified Data Engineer
            Associate announcement.
Image:      ../novalake-architecture.png (the full architecture diagram)
Links:      Repo link goes in the FIRST COMMENT, not the body — same convention
            as the original single-article post, so the post isn't
            reach-suppressed. No Medium links yet: the series publishes after
            this post, and each part's own LinkedIn post carries its link.
Body:       2,946 chars (LinkedIn cap 3,000). Hook + thesis both land above
            the ~210-char fold.
-->

# LinkedIn — series introduction

## 1. POST BODY

I built a Databricks lakehouse end to end, solo, on Free Edition.

Nine tagged releases. The write-up is mostly about the parts that didn't work.

Raw events → Bronze (PySpark) → Silver → Gold (dbt) → a serving layer → a GenAI layer, then the whole thing re-run at ~5,000,000 events to do Spark optimization on data big enough for the numbers to mean anything.

I'm publishing it as an 8-part build log starting this week. This post is the map.

Two things made it worth writing down.

The data is broken on purpose. Not a clean CSV — a synthetic payments event stream with 10 polymorphic event types, schema drift between versions, a field that's a struct 97% of the time and a bare string the other 3%, epoch-zero and year-2099 timestamps, ~1.5% replayed event IDs, and currencies arriving as "usd", " GBP" and "US$". The second source is paginated JSON API pages, 3-4 levels deep, with drift across pages.

And Claude Code was my pair throughout, on a deliberately short leash: four escalation stages, from zero write access to individually-gated live workspace actions, every side-effecting call logged with its exact parameters and outcome. Because a bad file change leaves a git diff. A bad live action leaves nothing.

I also passed the Databricks Certified Data Engineer Associate exam on Sunday. It's in this post rather than its own, because the two are the same thing: most of what that exam covers — Delta, Unity Catalog, the medallion split, incremental ingest, orchestration, governance — I'd already had fail on me in a specific, traceable way, and written down why.

The eight parts:

1 → The collaboration model. Four stages of AI access, each with a written trigger, a written scope, and a written log.

2 → Bronze. An audit tool that reported zero findings for an entire category, because the check itself was broken.

3 → Silver and Gold. 101 dbt models, and the one missing SQL keyword that would have silently dropped a fifth of the table.

4 → Serving and CI/CD. Guardrails written for a text-to-SQL model rather than an analyst — and a deploy pipeline that had been failing silently for three merges.

5 → The GenAI layer. My own agent handed over its full system prompt to the first probe anyone would try.

6 → DLT vs dbt. The same Silver slice built twice, into parallel schemas — plus an undocumented Free Edition quota I only found by querying the API directly.

7 → Four Spark experiments on a 2,138,809-row table, including an 86% improvement that turned out to be caused by nothing at all.

8 → The scorecard — including the one result I chased three different ways and published as unresolved.

The failures are in there deliberately. A build log where everything worked is a marketing document, and every engineer who has actually shipped something can tell. The specific error message is the part that transfers.

Part 1 lands this week. Repo in the comments.

#Databricks #DataEngineering #ApacheSpark #dbt #AI

---

## 2. FIRST COMMENT (post immediately after publishing)

Repo is public — 12 immutable ADRs, a filled-in phase doc per module, and the dated log of every gated AI action taken against the live workspace, including the ones that went wrong: https://github.com/ChiragVenkateshaiah/novalake
