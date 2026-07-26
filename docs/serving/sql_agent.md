# v0.6 Serving — Text-to-SQL Supervisor Agent Spec

Implements `docs/06-genai.md` Step 6.9. Same pattern as
`docs/serving/support_assist_agent.md` (Step 6.6) — built and deployed by
Claude under [ADR-0009](../adr/0009-agentic-integration-mcp-gated-review-then-act.md)'s
MCP-gated review-then-act discipline, every live action logged in
`docs/checkpoint.md`'s revisit log.

## Display name & purpose

**Supervisor Agent:** `NovaLake Analytics Assistant`
(`tile_id: 1b6eda83-e2d8-4cdb-8121-f8c51061fcaa`)
**Endpoint name:** `mas-1b6eda83-endpoint`
**Wraps:** the existing "NovaLake Gold Analytics" Genie space
(`space_id: 01f184ef1ae217509fe577597f00deb6`, built at `v0.4`) — no new
tables, indexes, or data; this is an orchestration layer, not a new data
surface.

A natural-language analytics assistant for NovaLake's Gold-layer business
data (transactions, refunds, payouts, support-ticket metrics, reviews,
risk, auth, KYC) — answers quantitative/aggregate questions by routing to
the Genie space's SQL generation. It has **no access to free-text ticket or
review content** — that's the support-assist agent's surface
(`docs/serving/support_assist_agent.md`, Step-group A), a deliberately
separate consumer so the two surfaces' very different guardrail concerns
(SQL-aggregate correctness here vs. retrieval-groundedness there) don't get
tangled into one agent.

## Guardrails carried forward

Every guardrail already curated into the Genie space (`docs/serving/genie_space.md`'s
General Instructions, certified example question/SQL pairs, and the
structural exclusion of `original_transaction_id`/`related_transaction_id`
from table scope) is inherited as-is by wrapping the space via
`genie_space_id`, not re-declared. The MAS's own `instructions` add exactly
one thing on top: an explicit scope boundary telling it to decline
free-text content questions rather than let the underlying Genie space
attempt (and fail at) something it has no data for.

## Access control

Checked directly (`serving-endpoints get-permissions` on the endpoint),
not assumed — same minimal pattern as every other surface in this project:
`CAN_MANAGE` for Chirag (explicit) and the `admins` group (both explicit
and inherited from `/serving-endpoints`) — no broader grant. The underlying
Genie space's own access control was already established at `v0.4` and is
unchanged by this wrapping layer.

## Known limitations (found via Step 6.8's offline eval, not theoretical)

- **Certified-example SQL reuse is non-deterministic — the standing
  limitation of this surface, not a one-time bug.** The same literal
  question, asked in separate conversations, has been observed to
  correctly reuse the Genie space's certified, guardrail-compliant SQL on
  one attempt and free-generate a different (differently-aggregated) query
  on another. Verified directly against the Genie space via `ask_genie`,
  isolated from the MAS layer. There is no fix available from the
  consuming side — this is inherent to how certified examples bias, rather
  than deterministically pin, the underlying SQL-generation LLM. **Do not
  treat a single passing validation run (including this doc's own, below)
  as proof the pinning holds reliably** — see
  `docs/serving/genie_space.md`'s caveat and `docs/06-genai.md` Step 6.8
  for the full evidence trail. Practical implication: for any
  guardrail-sensitive number reported from this surface, prefer
  re-verifying against `execute_sql` directly if the stakes are high,
  rather than trusting a single Genie/MAS answer.
- **MAS rewrites the user's question before invoking the Genie tool.**
  Observed directly in tool-call traces (e.g. a literal certified question
  arrived at the Genie tool paraphrased). This is a second, independent way
  certified-question matching can fail beyond the non-determinism above —
  even a verbatim-matching user question isn't guaranteed to reach the
  Genie space as the same literal text.
- **Agent Bricks "examples" are unavailable on this workspace** — creating
  them fails with `MODEL_DISABLED` (the internal embedding model Agent
  Bricks examples depend on is disabled on this Free Edition workspace).
  Routing/scope behavior was validated to work correctly from
  `instructions` alone instead (Step 6.7's live queries); see
  `docs/06-genai.md` Step 6.7 for the full trail.

## Sample questions

The 6 certified pairs from `docs/serving/genie_space.md`, using the exact
catalog phrasing (not the relative "last quarter"-style sample-question
wording, which drifts with today's date):
1. What was our approval rate in Q1 2026, across both sources?
2. What's our overall refund rate, and how does it vary by source?
3. What's our SLA breach rate by priority?
4. What fraction of transactions were risk-flagged, and separately, what fraction of risk alerts led to an auto-block, by source?
5. What's the average rating by merchant category?
6. What's our authentication success rate, by MFA usage?

(Full eval set, including the 2 new Step 6.8 extension cases and their
execution-grounded expected facts: `src/genai/sql_eval_dataset.py`.)

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-26 | Initial spec, written after Steps 6.7 (build/wrap) and 6.8 (eval, non-determinism finding) were both complete — confirms current live state and access-control posture, same convention as `support_assist_agent.md`. | Chirag + Claude |
