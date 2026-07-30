A GitHub Actions run passed. Green check, required check satisfied, PR mergeable.

It was also, quietly, wrong.

The workflow was `bundle validate` against my Databricks Asset Bundle. It parsed the YAML, resolved the target, reported success — exactly what it's supposed to do.

But I hadn't pinned `root_path` in `databricks.yml`. So the `dev` target resolved to whichever identity was deploying's own home folder. Locally that was mine. In CI it was the service principal's Application-ID folder.

The next step, `bundle deploy`, would have created a parallel job and a parallel dashboard under the service principal's folder — sitting next to the real ones, silently defeating every least-privilege grant I'd just spent an hour scoping.

Nothing would have failed. There would just have been two of everything.

I caught it by reading the CI log output, which prints the resolved path, instead of looking at the badge.

That's the whole project in one incident: a green checkmark isn't proof of correctness. It's proof that one specific check didn't fail.

I've just published the first of an 8-part build log for NovaLake — a Databricks lakehouse taken end to end on Free Edition. Raw events → Bronze (PySpark) → Silver → Gold (dbt) → Serving → a GenAI layer, orchestrated by a Databricks Asset Bundle, shipped as 9 tagged releases.

Part 1 is about the part most "I built X with AI" writeups get wrong: the collaboration model.

I ran a four-stage escalation, each stage with a written trigger, a written scope, and a written log. Fully hands-off through v0.4. Draft-and-approve at v0.5. Gated review-then-act from v0.6, where every side-effecting call had to present its exact parameters and wait for a go-ahead.

Two rules made it survivable rather than theatrical:

→ Every executed gated action gets logged, dated, with parameters and outcome. A skipped log entry for a file change still leaves a git diff. A skipped log entry for a live workspace action leaves nothing at all.

→ Deleting a wrongly-created live resource is itself a gated action. There is no `git revert` for a provisioned Vector Search endpoint.

Did it hold? Mostly. The interesting data is where it didn't — including a deploy that recreated an endpoint I'd deliberately deleted, twice, before the third proposal named that side effect up front.

Part 1 of 8 → LINK-PART-1

#Databricks #DataEngineering #PySpark #dbt #AI
