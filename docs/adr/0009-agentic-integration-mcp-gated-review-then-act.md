# ADR-0009: Agentic integration for v0.6+ — MCP-gated, review-then-act

**Status:** Accepted
**Date:** 2026-07-24
**Related:** [`docs/checkpoint.md`](../checkpoint.md) (`v0.6` re-open — this
ADR is the formal record the checkpoint's revisit-log entry points to),
[ADR-0006](0006-secret-based-service-principal-auth-for-cicd.md) (precedent
for checking platform capability/cost directly rather than assuming, and for
scoped, least-privilege identity access)

## Context

`docs/checkpoint.md` named `v0.6` as its explicit "Next re-open" point: the
place where "the actual agentic-integration architecture (Claude Code CLI +
Databricks MCP servers used for real, human-review gate on every diff) gets
designed, not just individual exceptions granted phase by phase." Its "What
to design when we get here" section, drafted at project kickoff as
placeholder guidance rather than a decision, sketched a shape: Databricks-
managed MCP servers as the integration surface, a `CLAUDE.md`-driven local
pattern, a review gate on every diff before `bundle deploy`, the existing
`bundle validate` CI gate, and starting narrow.

Since that placeholder was written: `.mcp.json` was wired at the repo root
(`databricks` MCP server, `defer_loading: true`); `v0.4`/`v0.5` each produced
one-off, explicitly-requested exceptions to "no agent workspace-write access"
(logged in `checkpoint.md`'s revisit log, never treated as standing rule
changes — the `manage_dashboard` read-only export at `v0.4`, then `bundle
deploy` + `manage_dashboard(publish)` for the same dashboard, and finally
`v0.5` landing on "Claude drafts every file, Chirag applies/deploys
everything himself" for CI/CD).

`v0.6` (RAG via Vector Search, then Agent Bricks text-to-SQL over the
existing Genie space) needs more than file drafting. RAG/agent iteration is
inherently exploratory — the useful signal (does this index return sane
results, does this agent config actually work) only comes from running the
thing, repeatedly. Hand-drafting `resources/vector_search.yml` and having
Chirag run every `bundle deploy` for every iteration is the `v0.5` pattern;
it doesn't scale to that loop.

## Decision

From `v0.6` onward, Claude may invoke Databricks MCP actions with side
effects — directly, not only by drafting files for Chirag to apply — but
every such action is gated by explicit review first. This is **review-then-
act**, not autonomy:

1. **Before any gated action, Claude presents the exact MCP tool call and its
   full parameter set** — not a prose summary. For a Vector Search index,
   that means endpoint name and type (storage-optimized vs. standard),
   source table, embedding model, embedding dimension, sync mode, and any
   sizing/scaling parameter the tool exposes — the same level of specificity
   ADR-0006 used for exact env vars and client IDs, not a paraphrase like "creating an index on the tickets table." Chirag gives explicit go-ahead
   before the call executes.
2. **The read-only carve-out is an explicit allowlist, default-gated
   otherwise** — not a fuzzy read/write line:
   - **Ungated:** `list`/`get` calls on any resource type; `query_vs_index`;
     `execute_sql`/`execute_sql_multi` classified *by statement* — only
     `SELECT`/`SHOW`/`DESCRIBE`/`EXPLAIN` qualify, regardless of which tool
     wraps them.
   - **Gated (named explicitly, so nothing is gated-by-omission):**
     `execute_code` (arbitrary Python on Databricks compute — not read-only
     under any definition); any non-`SELECT` `execute_sql`/`execute_sql_multi`
     statement; `manage_vs_endpoint`, `manage_vs_index`, and `manage_vs_data`
     (the last is an index *upsert* — easy to mentally file under "just
     search," it is a write); `manage_genie`, `manage_ka`, `manage_mas`
     create/update/delete calls; `manage_uc_objects`,
     `manage_uc_grants`/`manage_uc_security_policies`, and
     `manage_workspace`/`manage_workspace_files` writes.
3. **Every executed gated action is logged to `docs/checkpoint.md`'s
   revisit-log** — dated, naming the tool call, parameters, and outcome. File
   changes are already visible in git history; live MCP actions are not, so
   the audit trail has to be written deliberately or it doesn't exist. This
   generalizes the pattern already used to log `v0.4`'s one-off write
   exceptions into a standing rule instead of a per-incident write-up.
4. **Cost and blast-radius are part of what gets reviewed, not assumed
   away.** Before the first Vector Search endpoint or Agent Bricks resource
   is created, check this Free Edition workspace's actual availability,
   quota, and billing model directly — the same "verify the platform before
   assuming" discipline ADR-0006 (no OIDC) and ADR-0008 (no Spark UI/cluster
   knobs) already established for this project, applied here before the
   first live create rather than after hitting a wall. A wrongly-created
   live resource has no `git revert`; **deleting it is itself a gated
   action**, not a unilateral cleanup step Claude takes on its own judgment.
   Resource *sizing* is part of what Chirag approves, not just resource
   *existence*.
5. **`bundle validate` remains the CI gate** (`v0.5`, unchanged) for anything
   also expressed as bundle IaC — MCP-gated actions and bundle-authored
   resources are not mutually exclusive; where a resource type has bundle
   support, it still goes through the file-diff + PR + CI path like the
   dashboard did at `v0.4`/`v0.5` (see Alternatives below for how this
   interacts with the decision).
6. **Start narrow.** One Vector Search index, created and queried
   end-to-end, reviewed fully, before Agent Bricks or a second index is
   attempted — the original placeholder's "scope at first" guidance, now a
   concrete first step rather than a principle.
7. **Identity-sensitive actions stay hands-on regardless.** Any new service
   principal or secret continues to be created directly by Chirag, same
   carve-out `v0.5`'s `novalake-cicd` already established — this ADR governs
   what Claude does with Databricks resources, not workspace identity.

This decision supersedes and fulfills `docs/checkpoint.md`'s "what to design
when we get here" placeholder. That section stays in the file as history,
per `checkpoint.md`'s own convention of narrating reversals rather than
silently editing them; this ADR is the decided, formal version of it.

## Consequences

- From `v0.6` on, Claude can create, modify, and delete real Databricks
  resources without Chirag executing every CLI command or MCP call himself
  — the first phase where this is true. The exploratory RAG/agent-config
  loop this phase needs becomes possible: the read/query/eval side
  (`query_vs_index`, `SELECT`-only `execute_sql`) is ungated and can iterate
  freely, while every write is still gated per-action (see next bullet) —
  it's the read-heavy iteration loop that's freed, not unattended writes.
- Every gated action still requires Chirag's explicit go-ahead per action,
  not per phase — he can revoke or tighten this at any specific action if
  its blast radius is unclear, the same way any individual `v0.5` file diff
  could be rejected.
- `docs/checkpoint.md`'s revisit-log gains a matching dated entry pointing
  here; that entry carries the narrative, this ADR carries the one-decision
  record — same split used for the DAB-timing reversal (`checkpoint.md` +
  ADR-0001/0002).
- The live-action audit trail depends on this being followed consistently —
  unlike a file diff, a skipped log entry for an executed MCP action leaves
  no trace at all. This is a real discipline cost, not just a formality.
- Future phases (`v0.7` Declarative Pipelines, `v0.9` Spark optimization)
  inherit this same review-then-act pattern by default unless a later ADR
  narrows or widens it — this is written as the standing rule from here
  forward, not a `v0.6`-only carve-out.
- Before RAG build work actually starts, someone needs to check whether DAB
  currently supports a Vector Search / Genie Space / Agent Bricks resource
  type at all (today, the Genie space is hand-built with no bundle resource,
  unlike the dashboard) — this determines how much of `v0.6`'s work actually
  needs the MCP-gated path at all versus the existing file-diff+CI path. Not
  resolved by this ADR; a concrete build-time check (`databricks-bundles`
  skill), not a scoping-time assumption either way.

## Alternatives considered

- **Author Vector Search / Agent Bricks as DAB bundle resources where
  expressible, keep `v0.5`'s file-diff + `bundle validate` gate exclusively,
  and never grant direct MCP write access.** This is the honest alternative
  to steelman, not a strawman: it is exactly how the dashboard was handled
  at `v0.4`/`v0.5`, and if DAB turns out to fully support the resource types
  `v0.6` needs, it would keep every change in git history with no separate
  audit-log discipline required. It's rejected as the *sole* path — not
  categorically — because RAG/agent iteration is exploratory in a way the
  dashboard wasn't: tuning an index or an agent's retrieval behavior needs
  to actually run against live data repeatedly, and routing every single
  iteration through a full `bundle deploy` cycle doesn't fit that loop.
  Where DAB *does* support a given resource type, this ADR's §5 keeps that
  path — the two aren't exclusive; MCP-gated action covers the genuine gap,
  not everything.
- **Keep `v0.5`'s "Claude drafts files only, Chirag runs everything"
  pattern for `v0.6` too, with no exception.** Rejected for the reason
  above: it doesn't scale to the exploratory nature of RAG/agent
  iteration, where the useful signal only comes from actually running the
  thing.
- **Full autonomy — no per-action review gate.** Rejected. Matches
  `checkpoint.md`'s original placeholder reasoning (the industry pattern
  that's converged on is "agent proposes, human reviews, CI validates," not
  full autonomy) and Chirag's explicit boundary for this phase.
- **Gate only bundle-IaC file diffs, treat direct MCP actions outside the
  bundle as ungated.** Rejected — inverted from where the actual risk sits
  for `v0.6`. A live Vector Search index or Agent Bricks resource created
  via MCP *is* the primary risk surface this phase introduces (a real,
  potentially costly or wrong-schema live resource), not a secondary one
  next to file changes; gating only the file-diff side would leave the
  riskier side unreviewed.
