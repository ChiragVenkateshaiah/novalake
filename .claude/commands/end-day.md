---
description: End-of-day wrap-up — summarize today's progress, check git branch/status, and hand off to tomorrow's /start-day
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(git fetch:*), Bash(git stash list:*), Bash(gh pr view:*), Bash(gh pr checks:*), Bash(gh pr list:*), Read, Glob, Write(.claude/session-handoff.md)
---

Close out a work session on NovaLake with a short wrap-up. Do the following, in order, then summarize — do not commit, push, stage, stash, or otherwise change repo state, with exactly one exception: writing `.claude/session-handoff.md` (step 5 below). That file is gitignored (`.claude/*` except `commands/`), so overwriting it is not a repo-state change in any git-visible sense.

1. **Today's task** — if this session already discussed what was planned for today (e.g. it followed a `/start-day` briefing or an explicit plan earlier in this conversation), summarize progress against that specific task. If no such context exists in this conversation, do not invent or infer a "planned task" that was never actually stated — fall back to reporting only what git shows in step 2.
2. **Git evidence of today's work** — run `git log --oneline --since=midnight` for commits made today, and `git diff --stat` + `git diff --cached --stat` for unstaged/staged changes still outstanding.
3. **Git state for sign-off** — run `git fetch --quiet` (read-only, just updates remote-tracking refs) so the next check is accurate, then `git status -sb` for current branch, ahead/behind `origin/main`, and untracked files. Also run `git stash list` and flag any entries — a forgotten stash is unbacked-up work. If the current branch is `main` and there are any commits since midnight or uncommitted/staged changes, call that out explicitly (this repo's convention is branch-per-module; work on `main` outside a release tag is a hazard, not just a naming nitpick). Otherwise, note whether the branch matches the `feat/vX.Y-phase` convention for whatever phase is in progress (check README's roadmap/status if unclear).
4. **Open PR status** — if the current branch has an open PR (`gh pr view --json number,title,state,url` — ignore errors if none exists), note its number/URL and run `gh pr checks` to report which CI checks are passing/failing/pending. This matters even if nothing merged today — an open PR with passing CI but not yet merged is a real, specific state tomorrow's session needs to know, not just "branch exists."
5. **Definition of Done check** — glob `docs/*.md` to see which phase docs exist. If today's work plausibly completes a module (per CONTRIBUTING.md's DoD checklist), note which DoD boxes look satisfied vs. outstanding, based only on what's evidenced by git log/diff and doc file presence — don't guess at things you can't see.
6. **Write the handoff** — compose a short handoff note (the same content as the wrap-up below, condensed) and write it to `.claude/session-handoff.md`, **overwriting** any existing content (this file reflects only the *most recent* end-of-day, never accumulates history). Include: date, current branch, open PR number/URL + CI status if any, what got done today (bullet list), what's outstanding and why it wasn't finished (e.g. "merge withheld deliberately — deploys to live resources"), and the single most concrete next action. If nothing meaningful happened this session (no commits, no PR, no outstanding work), don't write a hollow file — skip this step and say so in the wrap-up instead.

Then give a concise wrap-up (not a wall of text):
- What got done today (from conversation context and/or git log) — or "no commits today" if git shows none
- Open PR status if any (number, URL, CI check results)
- Outstanding uncommitted/unstaged/stashed work, if any, and the risk of leaving it (none of it is backed up to origin)
- Current branch, ahead/behind `origin/main`, and the on-`main` warning if it applies
- A suggested commit message for outstanding work, if there is any worth committing — suggest only, never run
- DoD status if a module looks close to done, otherwise skip this bullet
- Confirm whether `.claude/session-handoff.md` was written (and one line on what it says), or that it was skipped because there was nothing to hand off

End with the wrap-up. Do not commit, stage, push, stash, or modify any file other than `.claude/session-handoff.md` — just report so the user can decide what to do before closing out.
