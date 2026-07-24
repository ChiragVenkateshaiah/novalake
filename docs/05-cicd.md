# Module 5 · CI/CD

`Status:` Complete  ·  `Owner:` Chirag  ·  `Last updated:` v0.5 (complete, 2026-07-24)  ·  `Est. time:` ___

## 1. Learning Objectives
- [ ] Can evaluate whether a platform actually supports a stated best
      practice (OIDC/federated CI auth) instead of assuming it, and choose
      the correct fallback when it doesn't
- [ ] Can design a CI deploy gate that fails safe on a destructive plan
      instead of blindly auto-approving it, informed by a real incident
      (`v0.4`'s dashboard delete+recreate) rather than a hypothetical one
- [ ] Can recognize when a "prod" distinction would be a semantic overlay
      rather than real environment isolation, and scope the phase to what
      the platform actually supports instead of building a facsimile
- [ ] Can hand a new CI identity least-privilege access explicitly, instead
      of accepting whatever a creation UI defaults to

## 2. Prerequisites
- Completed modules: `v0.4` Serving (Genie space + dashboard, wired into
  the bundle and deployed — see `docs/04-serving.md`), tagged `v0.4`
- Tables / assets that must already exist: `resources/dbt_job.yml`,
  `resources/dashboard.yml` (both already deployed under `dev`)
- Compute / cluster config: unchanged — Serverless SQL warehouse
  ("Serverless Starter Warehouse"), serverless job/dbt environments
- New prerequisite specific to this module: a service principal
  (`novalake-cicd`, Application ID `3ee2f464-5c6c-4aee-b1b8-792210883a3a`)
  created by hand in Workspace settings → Identity and access → Service
  principals, with its OAuth client secret generated and stored directly
  as the GitHub Actions repo secret `DATABRICKS_CLIENT_SECRET`

## 3. Where This Fits (Architecture Context)
- One-line: automates deployment of the existing bundle (Bronze→Silver/
  Gold job, Serving dashboard) via GitHub Actions, using a service
  principal instead of a personal profile — doesn't touch what the bundle
  deploys, only who/how it gets deployed
- Reference diagram: `docs/architecture.md` (unchanged by this module —
  CI/CD is a deploy-path change, not a data-flow change)
- Inputs → this module → Outputs: `databricks.yml` + `resources/*.yml`
  (existing, `dev`-validated) → CI/CD (GitHub Actions, `dev` target,
  service-principal auth) → the same job/dashboard, now deployed by CI
  instead of by hand
- **No `prod` target.** This project has one Free Edition workspace; a
  same-workspace `prod` would only be a semantic overlay (different
  deploying identity, same everything else), not real environment
  isolation. Real production semantics — genuine promotion, infrastructure
  proven reproducible from scratch — are out of scope for NovaLake
  entirely; see [ADR-0007](adr/0007-defer-prod-no-same-workspace-production-semantics.md)
  and [ADR-0008](adr/0008-novalake-terminus-and-cerberus-succession.md)
  (NovaLake's terminus at `v0.9`, succeeded by a new project, Cerberus, on
  AWS/Terraform, where that actually belongs).

## 4. Concepts & Background
- **OIDC/federated auth vs. secret-based auth.** OIDC removes a standing
  credential entirely — GitHub issues a short-lived token per run,
  Databricks trusts it via a federation policy, nothing to store or
  rotate. Checked directly against this workspace (service principal
  detail page: Configurations/Permissions/Secrets/Git integration tabs
  only, no Federation policies tab; no separate Account Console reachable
  from a Free Edition workspace) — not available here. See
  [ADR-0006](adr/0006-secret-based-service-principal-auth-for-cicd.md).
- **Fail-safe vs. auto-approved destructive deploys.** `bundle deploy`
  without `--auto-approve` refuses to apply a plan requiring deletion or
  recreation of a resource — it exits non-zero and leaves the workspace
  untouched instead. This is the same protection that caught a real
  Lakeview-dashboard delete+recreate by hand during `v0.4` (see
  `docs/checkpoint.md`, 2026-07-22); an unattended `--auto-approve` CI run
  would have applied that recreate silently.
- **A shared target needs auth that works for two different identities.**
  `dev` is used both interactively (Chirag, personal OAuth) and by CI
  (`novalake-cicd`, env-var auth). A hardcoded `workspace.profile: DEFAULT`
  in the target would make CI look for a `DEFAULT` profile that doesn't
  exist in the GitHub Actions runner instead of falling back to its env
  vars — the fix was removing the pinned profile from `databricks.yml`
  entirely and supplying it externally either way (`-p DEFAULT` locally,
  env vars in CI).
- **A creation UI's default isn't automatically the right scope.**
  `novalake-cicd` was auto-added to the `admins` group when created via
  the Workspace settings UI — not a deliberate choice, just what the
  "Add service principal" flow defaulted to. A full workspace-admin CI
  identity is a much bigger blast radius than "can deploy this one
  bundle" — if `DATABRICKS_CLIENT_SECRET` ever leaked, that's a full
  workspace compromise, not just this project's job/dashboard. Fixed by
  removing it from `admins` and granting exactly what it needs instead
  (see §6.2/§8).
- Common pitfalls / gotchas to watch for: workspace folder ACLs are
  protected per-identity — one identity can't `mkdir` inside another
  identity's home folder (hit this validating a since-abandoned `prod`
  design locally, using personal credentials against a path meant for the
  service principal); Unity Catalog privileges are a separate system from
  workspace-admin group membership — being in `admins` does not grant
  catalog/schema access, that still needs explicit `GRANT`s regardless.

## 5. Data Contract / Schema in Scope
- Source schema (expected): no new tables — this module doesn't touch
  `novalake.silver.*`/`novalake.gold.*`, only how the bundle that produces
  them gets deployed and who's allowed to
- Target schema (produced): not applicable — deploy-path change only
- Schema-evolution policy: not applicable
- Keys / grain / uniqueness: not applicable

## 6. Step-by-Step Implementation
- **Step 6.1 — Service principal + auth mechanism decision**
  - *Objective:* establish a real CI identity and confirm which auth
    mechanism this workspace actually supports, rather than assuming
  - *Task:* create `novalake-cicd` by hand (Workspace settings → Identity
    and access → Service principals); check its detail page for an OIDC
    federation option before defaulting to secret-based auth
  - *Expected output:* [ADR-0006](adr/0006-secret-based-service-principal-auth-for-cicd.md)
    recording the finding (no federation tab, no reachable Account
    Console) and the resulting decision
  - *Validation check:* Application ID visible in the Service principals
    list; OAuth secret generated and stored as `DATABRICKS_CLIENT_SECRET`
    in GitHub — done 2026-07-22, Chirag created the SP and secret by hand,
    Claude never saw the secret value
- **Step 6.2 — Least-privilege access for `novalake-cicd`**
  - *Objective:* let the service principal manage the *existing* `dev`
    job/dashboard (it isn't the identity that originally created them),
    without the workspace-admin access it got by default on creation
  - *Task:* remove `novalake-cicd` from the `admins` group (SCIM group
    patch); grant explicit `CAN_MANAGE` directly on three objects — the
    bundle's deployment folder (`/Workspace/Users/chiragvenkatesh92@gmail.com/.bundle/novalake/dev`),
    the job (`[dev] novalake bronze-to-silver`), and the dashboard
    ("NovaLake Gold Analytics"); grant Unity Catalog `USE_CATALOG` on
    `novalake` and `USE_SCHEMA`/`SELECT`/`MODIFY`/`CREATE_TABLE` on
    `bronze`/`silver`/`gold` (warehouse access already covered — the
    `users` group has `CAN_USE` on the SQL warehouse independent of
    `admins` membership)
  - *Expected output:* narrowed, explicit ACLs — done directly via CLI
    (`databricks groups patch`, `databricks workspace/jobs
    update-permissions`, `databricks grants update`) once Chirag confirmed
    the least-privilege direction over leaving it as admin
  - *Validation check:* `databricks service-principals list` shows no
    `groups` field for `novalake-cicd` (removed from `admins`); each
    `update-permissions`/`grants update` call's response confirms the new
    ACL — done 2026-07-22; whether it's *sufficient* (vs. missing some
    grant only a real deploy would surface) isn't confirmed until CI
    actually runs
- **Step 6.3 — `databricks.yml`: drop the pinned `dev` profile**
  - *Objective:* let both a human (personal OAuth) and CI (service
    principal, env vars) authenticate against the same `dev` target
  - *Task:* remove `workspace.profile: DEFAULT`; add `workspace.host`
    explicitly so both auth paths still know which workspace regardless
    of who's authenticating
  - *Expected output:* updated `databricks.yml`
  - *Validation check:* `databricks bundle validate -t dev` still passes
    (using `-p DEFAULT` locally now that the profile isn't implicit) —
    **but this validation was misleading**: it only exercised *my*
    identity locally, and `root_path` was still unpinned at this point.
    The first real CI run (PR #5) resolved `root_path` to `novalake-cicd`'s
    *own* home folder instead of Chirag's, since it defaults to whichever
    identity is deploying. Caught only because that run's log was actually
    read, not just its pass/fail status — `bundle-deploy` would have
    created a parallel job/dashboard under the service principal's home
    instead of adopting the existing ones, silently defeating the whole
    point of §6.2's grants. Fixed by pinning `root_path` explicitly to
    Chirag's folder; second CI run confirmed the correct path resolves
    for either identity
- **Step 6.4 — GitHub Actions workflows**
  - *Objective:* a required PR check (`bundle validate`) and an
    auto-deploy-on-merge (`bundle deploy`) that fails safe on destructive
    plans
  - *Task:* two workflows, `bundle-validate.yml` (on `pull_request` to
    `main`) and `bundle-deploy.yml` (on `push` to `main`); both target
    `dev` (no `prod`), authenticate via `DATABRICKS_HOST`/
    `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` env vars, no CLI
    profile; both pin `actions/checkout` and `databricks/setup-cli` to
    commit SHAs (not `@main`) since these workflows hold a decrypted
    secret in their environment; deploy deliberately omits
    `--auto-approve`
  - *Expected output:* `.github/workflows/bundle-validate.yml`,
    `.github/workflows/bundle-deploy.yml`
  - *Validation check:* not yet run for real — first real trigger is
    opening the PR that merges this branch

## 7. Operational Considerations
- Idempotency / re-run safety: `bundle deploy` is idempotent for
  non-destructive changes (updates in place); destructive changes fail
  the run instead of applying — see §4
- Incremental vs full refresh: not applicable — deploy-path change only
- Performance (partitioning / clustering / file sizing): not applicable
- Failure & retry behaviour: a failed `bundle-deploy` run leaves the
  previous `dev` deployment untouched (nothing applied, DAB deploys are
  all-or-nothing per resource); re-running after fixing the underlying
  issue is safe

## 8. Data Quality & Governance
- Expectations / rules applied: not applicable — no data models in scope
- Quarantine / reject handling: not applicable
- Lineage & catalog tags: not applicable
- Ownership & access: `novalake-cicd` holds exactly — `CAN_MANAGE` on the
  `dev` bundle folder, the job, and the dashboard; Unity Catalog
  `USE_CATALOG` on `novalake` and `USE_SCHEMA`/`SELECT`/`MODIFY`/
  `CREATE_TABLE` on `bronze`/`silver`/`gold`; no workspace-admin
  membership. Whether this is complete won't be fully known until CI
  actually runs and either succeeds or surfaces a missing grant.

## 9. Validation & Acceptance Criteria
- [x] `bundle-validate.yml` passes as a required PR check on this
      branch's own PR — done 2026-07-22, PR #5. First run passed but
      resolved the wrong deploy path (CI's identity's own home folder,
      not Chirag's — see §6.2/Changelog); fixed by pinning `root_path`
      explicitly, second run confirmed the correct path resolves
      regardless of deploying identity
- [x] `bundle-deploy.yml` successfully deploys `dev` on merge to `main`,
      updating the existing job/dashboard in place (not creating parallel
      copies) — confirms the least-privilege grants in §6.2 are sufficient.
      Done 2026-07-24: PR #5 merged, `bundle-deploy.yml` ran in 41s and
      succeeded, log confirmed it uploaded to
      `/Workspace/Users/chiragvenkatesh92@gmail.com/.bundle/novalake/dev/files`
      (Chirag's folder, not `novalake-cicd`'s own home). Chirag manually
      verified in the workspace UI: exactly one `[dev] novalake
      bronze-to-silver` job and one "NovaLake Gold Analytics" dashboard —
      no parallel copies created.
- [x] Sign-off: Chirag — 2026-07-24

## 10. Key Takeaways
- A green CI badge isn't proof of correctness — `bundle-validate.yml`'s
  first real run passed while `root_path` was still silently resolving to
  the wrong identity's home folder. The bug was only visible by reading
  the run's actual log output, not its pass/fail status. Reading logs, not
  just checking checkmarks, is what caught it.
- Platform capabilities should be checked directly against the real
  environment, not assumed from general best-practice knowledge. OIDC
  federation is the better-practice CI auth pattern, but this Free Edition
  workspace doesn't expose it (no Federation policies tab, no reachable
  Account Console) — confirmed by opening the service principal's actual
  detail page, not inferred from documentation elsewhere.
- A same-workspace `prod` distinguished only by deploying identity is a
  semantic overlay, not real environment isolation — recognized and
  corrected (ADR-0007) before it shipped, not after.
- A creation UI's default isn't automatically the right scope: `novalake
  -cicd` was auto-added to `admins` on creation, which had to be
  deliberately walked back to explicit least-privilege grants. Trusting a
  wizard's default over verifying what it actually granted would have left
  a much bigger blast radius than the job needed.
- A shared target used by two different identities (a human locally, a
  service principal in CI) can't hardcode either one's auth into the
  bundle config — `workspace.profile` had to be dropped so both paths
  resolve their own credentials independently.

## 11. Knowledge Check
- **Q1: Why doesn't `databricks.yml`'s `dev` target pin `workspace.profile`
  anymore, and what would happen if it still did?**
  `dev` is now deployed by two different identities: Chirag locally
  (personal OAuth via a named CLI profile) and GitHub Actions
  (`novalake-cicd`, authenticated purely via `DATABRICKS_HOST`/
  `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` env vars, no CLI
  profile at all). If `workspace.profile: DEFAULT` were still pinned, CI
  would try to resolve a profile named `DEFAULT` from the runner's local
  CLI config — which doesn't exist there — instead of falling back to its
  env vars, and every CI run would fail on auth before ever reaching
  `bundle validate`/`bundle deploy`.
- **Q2: `bundle-validate.yml`'s first real run on PR #5 passed. Why didn't
  that catch the `root_path` bug, and what did?**
  `bundle validate` checks the bundle's schema and internal consistency —
  it doesn't simulate a deploy or resolve identity-dependent defaults
  against the live workspace the way `bundle deploy` does. `root_path` had
  no explicit value, so it silently defaulted to whichever identity was
  authenticated — `novalake-cicd`'s own home folder in CI, not Chirag's —
  and that default is a legitimate value from `validate`'s point of view,
  not an error. The bug was only caught by reading the actual CI log
  output (which prints the resolved path) rather than trusting the
  green checkmark alone; a `bundle-deploy` run would have created a brand
  new job/dashboard under the wrong home folder instead of adopting the
  existing ones, defeating the point of §6.2's scoped grants without ever
  failing loudly.

## 12. References
- Internal: `docs/checkpoint.md` (the `v0.5` re-open decision this module
  implements, and the pinned `v0.9` prerequisite from ADR-0008),
  [ADR-0006](adr/0006-secret-based-service-principal-auth-for-cicd.md),
  [ADR-0007](adr/0007-defer-prod-no-same-workspace-production-semantics.md),
  [ADR-0008](adr/0008-novalake-terminus-and-cerberus-succession.md),
  `docs/04-serving.md` (the dashboard-recreate incident this module's
  fail-safe deploy design is directly informed by)
- Databricks docs / skills used: `databricks-bundles` (target/mode/
  permissions shape), `databricks` (CLI auth guidance — explicitly warns
  against PATs in CI/CD)
- External: `databricks/setup-cli` GitHub Action, `actions/checkout`

## Changelog
| Date | Change | Author |
|------|--------|--------|
| 2026-07-22 | Module scaffolded. `v0.5` checkpoint re-open decision made (`docs/checkpoint.md`): Claude drafts every file, Chirag approves each one — landed after checking this workspace directly for OIDC support (not available) rather than assuming. `novalake-cicd` service principal + OAuth secret created by hand (Chirag); secret stored only as the GitHub repo secret `DATABRICKS_CLIENT_SECRET`, never seen by Claude. | Chirag + Claude |
| 2026-07-22 | First-pass design (a `prod` target) reworked after Chirag caught that it was a same-workspace semantic overlay, not real environment isolation. Reworked to: CI/CD automates `dev` (taking over the existing job/dashboard, not a parallel copy); `novalake-cicd` removed from `admins` (auto-added by the creation UI, not deliberate) and granted explicit least-privilege access instead (job/dashboard/bundle-folder `CAN_MANAGE`, UC grants on bronze/silver/gold); `databricks.yml` drops its pinned `dev` profile so both personal and CI auth work against the same target. Produced [ADR-0007](adr/0007-defer-prod-no-same-workspace-production-semantics.md) (supersedes ADR-0003's `prod`-at-`v0.5` timing) and [ADR-0008](adr/0008-novalake-terminus-and-cerberus-succession.md) (NovaLake terminus at `v0.9`; real prod/promotion/infra-Spark-tuning deferred to a new project, Cerberus). Both ADRs reviewed by Opus (second-model-pass) before acceptance; corrections folded in (v0.8 marked reserved rather than silently skipped, an honest rejected-alternative for paid-classic-compute Databricks, a softened serverless-caching claim). `bundle validate -t dev` confirmed passing throughout | Chirag + Claude |
| 2026-07-22 | PR #5 opened; `bundle-validate.yml` ran for real for the first time. First run passed but exposed a real bug only visible by reading the log, not just the pass/fail badge: with no explicit `root_path`, `dev` resolved to whichever identity was deploying's own home folder — `novalake-cicd`'s application-ID folder in CI, not Chirag's. Would have made `bundle-deploy` create a parallel job/dashboard instead of adopting the existing ones, silently defeating §6.2's grants. Fixed by pinning `root_path` explicitly in `databricks.yml`; second CI run confirmed the correct path for either identity. §9's first criterion checked off | Chirag + Claude |
| 2026-07-24 | PR #5 reviewed and merged to `main` (merge commit, matching repo convention). `bundle-deploy.yml` triggered automatically on the merge push and succeeded in 41s; log confirmed it deployed to Chirag's existing bundle path, not `novalake-cicd`'s own home. Chirag manually verified in the workspace UI: exactly one `[dev] novalake bronze-to-silver` job and one "NovaLake Gold Analytics" dashboard, no parallel copies. §9's second criterion checked off, sign-off given, module marked Complete. | Chirag + Claude |
