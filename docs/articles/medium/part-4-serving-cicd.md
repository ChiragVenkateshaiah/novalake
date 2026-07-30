<!--
MEDIUM METADATA — Part 4 of 8
Title:      Serving and CI/CD
Subtitle:   Guardrails against a model better at SQL than the guardrail — then a green checkmark that was quietly wrong. (110 chars)
Cover:      ../poster/part-4-serving-cicd.png
SEO title:  Serving and CI/CD: guardrails a model can't route around (55)
SEO desc:   Why one Genie guardrail had to be enforced by removing a column, the 0.7-point Simpson's paradox gap, and a CI pipeline silently failing for three merges. (157)
Tags:       Databricks, Data Engineering, CI CD, Text To SQL, Analytics
Source:     docs/articles/novalake-full-story.md — lines 206-266, verbatim
-->

# Serving and CI/CD

### Designing guardrails against a model that's better at SQL than the guardrail — and the phase where I built the wrong thing and then deleted it

*Part 4 of 8 in **The platform is the only source of truth**, a build log of a Databricks lakehouse taken end to end on Free Edition.*
*← Previous: [Silver and Gold](LINK-PART-3) · Next: [The agent that leaked its own system prompt](LINK-PART-5) →*

---

**Where we are.** [Part 3](LINK-PART-3) closed with Gold: 101 dbt models, conformed dimensions built only where identity genuinely conforms, and every rate computed from raw counts at a declared grain rather than averaged from another rate column. That last rule was written for this phase. Here is where the consumer stops being a human analyst and starts being a model.

---

## Serving — designing guardrails against a model that's better at SQL than the guardrail

Serving is where the project got genuinely interesting from a design standpoint, because the consumer is a text-to-SQL model with access to my Gold schema, and **a capable text-to-SQL model will find and use a technically-valid join that a human analyst would never think to try.**

I started by writing a shared question→SQL catalog *before* either consumer existed — 8 business domains plus a cross-domain question, with the certified SQL for each. That single artifact is what kept the Genie space and the dashboard from independently drifting into two different definitions of "approval rate."

Then the Genie space ("NovaLake Gold Analytics") got 7 numbered instructions, 6 certified question→SQL pairs, and a 16-question sample list. Four of those instructions are the guardrails I care most about:

1. Never combine FX-normalized USD totals (multiline-only) with native-currency totals from NDJSON in one figure. Label any USD total as multiline-only.
2. Never blend support-ticket performance across sources. Two separate answers, always.
3. Never join `fct_refunds` or `fct_support_tickets` to `fct_transactions` on `original_transaction_id` / `related_transaction_id`. Use aggregate ratios grouped by `(event_date, source)`.
4. Every `metric_*` rate column is pre-computed at a specific grain. Any question spanning a coarser grain must recompute the rate from the underlying counts the metric table also exposes — never average the rate column.

Plus three that are more "expected data quirk" than adversarial: `has_multiline_profile` sparsity is by design, `fct_payouts` has no `customer_id` at all so never attribute a payout to a customer, and `fct_transactions.merchant_id` is ~2% null on NDJSON by design.

**The guardrail that prose can't carry.** Instruction #3 is the one where I stopped trusting instructions. A prose instruction saying "don't join on this column" is a suggestion to a model that can see the column, notices it's named `original_transaction_id`, and correctly infers what that name usually means. So `original_transaction_id` and `related_transaction_id` were **structurally excluded from the Genie space's column visibility entirely** — done by hand in the workspace UI, because it wasn't achievable through the config options the API exposes. That's the one guardrail that curation, not instruction, has to carry.

**The guardrail that was worth a live test.** I asked the deployed space "what's overall support ticket performance," which spans a coarser grain than `metric_support_sla_breach_rate_multiline`'s `(event_date, priority)`. It correctly kept the two sources as separate answers *and* reported the overall breach figure as **47%** — the count-weighted recomputation from underlying counts. The naive unweighted mean of the per-priority rates is **47.7%**. A 0.7-point gap sounds trivial until you notice it's the exact shape of every Simpson's-paradox reporting bug: the number that's wrong is close enough to the number that's right that nobody questions it.

Two other live tests passed: "approval rate last quarter" correctly resolved to Q2 2026 relative to the actual current date, and "total transaction volume in USD this year" correctly labeled itself multiline-only.

### The dashboard found bugs the SQL review couldn't

The AI/BI dashboard is 3 pages and 11 datasets on Gold. Both of the real bugs in it were invisible to reading the SQL, which is the point:

1. A KPI dataset filtered on `year(current_date())`. The wall clock had moved into Q3 2026; the dataset's fixed range ends 2026-06-15. The tile rendered `null`. The SQL is *correct*; the bug is that it's anchored to the wall clock instead of to `max(date_day)` in `dim_date`.
2. A payout-latency chart silently **summed p50/p90 percentiles across `schedule_status`**. Counts are additive across a dimension; percentiles are not. Nothing in the SELECT statement is wrong — the bug lives in the chart's aggregation config. Fixed by adding `schedule_status` as a Facet.

Reviewing a query validates the query in isolation. Building the artifact validates the query *in its runtime context*, against the actual data range, under the visualization layer's own aggregation semantics. Those catch different bug classes and neither substitutes for the other.

### And then DAB wanted to delete my dashboard

Wiring the hand-built dashboard into the bundle, `bundle deploy` planned a **delete and recreate** — for two independent reasons: a `display_name` mismatch, and a `parent_path` mismatch (the bundle's default resources path versus where the dashboard actually lived). Lakeview dashboards can't rename or move in place.

Fixing the name wasn't enough, because there were two mismatches. And the fix I reached for first — `presets.name_prefix: ""` to suppress `mode: development`'s name prefix — was **silently ignored**, a Go zero-value quirk in the CLI that `bundle validate` doesn't warn about at all. Empty string is indistinguishable from unset. The actual fix was dropping `mode: development` entirely and re-declaring only the presets that mattered, plus an explicit `parent_path`. The safe path through was `databricks bundle deployment bind` before deploying, then verifying `dashboard_id` and `create_time` were unchanged afterward — proof the existing object was adopted, not replaced.

---

## CI/CD — the phase where I built the wrong thing and then deleted it

Two workflows: `bundle-validate.yml` on PR to `main` (path-filtered, required check), and `bundle-deploy.yml` on push to `main`, deliberately *without* `--auto-approve` so a destructive plan fails safe instead of executing. That second decision is a direct consequence of the `v0.4` dashboard incident — I'd already seen `bundle deploy` propose a delete-and-recreate once.

**OIDC was checked, not assumed.** Workload-identity federation is the better-practice option and I wanted it. So I created the service principal, opened its detail page, and looked: **exactly four tabs — Configurations, Permissions, Secrets, Git integration. No "Federation policies" tab.** The Secrets tab offers only "Generate secret." And the workspace URL is a workspace domain, not an account-console domain — Free Edition doesn't appear to expose a separate Account Console at all, which is where account-wide OIDC policies would live. So: secret-based OAuth M2M, client secret stored only as a GitHub repo secret, which I generated and stored myself. Recorded explicitly as a constraint of the platform tier, not a preference for secrets over federation.

**The service principal was over-privileged by default.** The creation UI auto-added it to the `admins` group. That got walked back deliberately: removed from `admins`, then granted explicitly — `CAN_MANAGE` on the bundle deployment folder, the job, and the dashboard; UC `USE_CATALOG` on the catalog and `USE_SCHEMA`/`SELECT`/`MODIFY`/`CREATE_TABLE` on `bronze`/`silver`/`gold`. A creation UI's default is a convenience, not a scope decision.

**I built a `prod` target, then deleted it.** The first pass at this phase added one: same workspace, same catalog, same data, distinguished only by the deploying identity and `mode: production`. Reviewing the thing I'd actually built made the problem obvious in a way that reviewing the *plan* hadn't: it's a semantic overlay, not environment isolation. "Promoting to prod" would have meant nothing more than "the robot deployed it instead of the human." Free Edition has exactly one workspace, and no amount of YAML changes that. So NovaLake has one target, `dev`, and always will — with real production semantics deferred to a successor project where they can actually exist.

**And then the `root_path` bug**, which is where this series opened. First real CI run of `bundle-validate.yml` passed. With no explicit `root_path`, `dev` resolved to whichever identity was deploying's own home folder. Caught by reading the log, not the badge. Pinned explicitly; the second run confirmed correct resolution for both identities. `bundle-deploy.yml` then ran on the merge in **41 seconds**, updated the existing job and dashboard in place, and I verified in the workspace UI that there was exactly one of each, no parallel copies.

`validate` does not simulate a deploy and does not resolve identity-dependent defaults against the live workspace. That's not a bug in `validate` — it's the boundary of what it claims to do, and I'd assumed a wider claim.

### Postscript: the same phase's bug, found four tags later

Here's the honest coda. After tagging `v0.9`, I checked a failed GitHub Actions run: `Bundle Deploy` failing with `403 PERMISSION_DENIED` — the CI service principal couldn't even *read* the new `v0.9` job or the `v0.7` DLT pipeline in order to plan against them.

`gh run list` showed this wasn't new. The same workflow had also failed on the `v0.6` and `v0.7` merges. The DLT pipeline never got a permissions grant when it was created, so **every automated deploy since had been silently failing at the planning step** — and the live workspace only stayed correct because every real deploy in that stretch happened to be run manually with my own credentials. A broken automation that nothing depends on looks exactly like a working one.

The fix attempt is the instructive part. The obvious move — declare a `permissions:` block on those resources in the bundle — stopped the read 403 and immediately produced a *different* failure: DAB then tries to reconcile the **entire ACL** including ownership, which the service principal can't touch. So the correct fix turned out to be the pattern the original job had been using since `v0.5` all along: grant `CAN_MANAGE` once, directly, via CLI, *outside* DAB's management. Reverted the `permissions:` block, applied the grant, and verified end to end by watching an actual `Bundle Deploy` run go green — 13m35s, no 403 of either kind.

Two lessons, both mildly humbling. Adding a resource type to a bundle is not the same as adding it to CI's permission surface, and nothing warns you. And the more general one: *check that your automation is still running, not just that it's still configured.*

---

**Next up — [Part 5: The agent that leaked its own system prompt](LINK-PART-5).** The first injection probe anyone would try, run against a careful rule-numbered prompt — and two scorer bugs that looked exactly like agent failures until I read the raw judge rationale.

*Part 4 of 8. Start at [Part 1](LINK-PART-1) · Full repo: [GitHub](LINK-REPO)*
