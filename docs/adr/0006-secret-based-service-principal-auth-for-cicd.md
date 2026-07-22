# ADR-0006: Secret-based service-principal auth for CI/CD, not OIDC federation

**Status:** Accepted
**Date:** 2026-07-22
**Related:** [ADR-0007](0007-defer-prod-no-same-workspace-production-semantics.md), [`docs/checkpoint.md`](../checkpoint.md) (`v0.5` re-open decision)

## Context

`v0.5` needs GitHub Actions to authenticate to Databricks to run `bundle
validate`/`bundle deploy` against `dev` (there is no `prod` target — see
[ADR-0007](0007-defer-prod-no-same-workspace-production-semantics.md)). Two ways to
authenticate a CI service principal to Databricks were considered:

1. **OIDC/workload-identity federation** — GitHub issues a short-lived OIDC
   token per workflow run, Databricks trusts it via a federation policy
   scoped to this repo. No client secret is ever generated or stored;
   nothing to rotate or leak.
2. **Secret-based OAuth machine-to-machine (M2M)** — a service principal's
   client ID + a generated client secret, the secret stored as an encrypted
   GitHub Actions repository secret and injected as an env var at runtime.

OIDC is the better-practice option when available — it removes a standing
credential entirely. It was checked directly against this project's actual
workspace before assuming either path: created a service principal
(`novalake-cicd`) via Workspace settings → Identity and access → Service
principals, then opened its detail page. That page exposes exactly four
tabs — **Configurations, Permissions, Secrets, Git integration** — no
"Federation policies" tab. The "Secrets" tab only offers "Generate secret"
(an OAuth client secret), nothing resembling an OIDC issuer/subject-claim
policy editor. The workspace URL itself
(`dbc-0fadb959-36a9.cloud.databricks.com`) is a workspace domain, not
`accounts.cloud.databricks.com` — Free Edition does not appear to expose a
separate Account Console at all, which is where OIDC federation policies
would normally be configured account-wide.

## Decision

Use secret-based OAuth M2M auth for `v0.5`'s CI/CD: the `novalake-cicd`
service principal's client ID (`3ee2f464-5c6c-4aee-b1b8-792210883a3a`,
non-sensitive) is used directly in the GitHub Actions workflows; its OAuth
client secret is stored only as the GitHub repository secret
`DATABRICKS_CLIENT_SECRET`, never committed, never shared in chat/logs. The
CLI resolves auth purely from `DATABRICKS_HOST`/`DATABRICKS_CLIENT_ID`/
`DATABRICKS_CLIENT_SECRET` env vars in each workflow. `databricks.yml`'s
`dev` target no longer pins `workspace.profile` for the same reason — a
hardcoded profile would make CI look for a profile that doesn't exist in
the runner instead of falling back to its env vars; Chirag's local runs now
pass `-p DEFAULT` explicitly instead of relying on the file for it.

## Consequences

- A real, rotatable credential now exists and must be treated as such: if
  `DATABRICKS_CLIENT_SECRET` needs to be rotated, generate a new secret on
  the service principal's Secrets tab and update the GitHub repo secret;
  the old one can then be revoked from the same tab.
- If Databricks later adds OIDC federation support to Free Edition (or the
  project moves to a workspace tier that has it), this ADR's decision
  should be revisited — the secretless path is still preferable in the
  abstract, this decision is a constraint of the current platform tier, not
  a preference for secrets over federation.

## Alternatives considered

- **OIDC/workload-identity federation.** Rejected for now, not on
  principle but because it was checked directly and isn't exposed by this
  Free Edition workspace's UI — no Account Console, no federation-policy
  editor found on the service principal's detail page.
- **Personal OAuth token / PAT in CI.** Rejected outright — this is
  exactly the anti-pattern the `databricks` skill's own CLI-auth guidance
  warns against for CI/CD (a personal credential with a human's full
  access, not a scoped service identity).
