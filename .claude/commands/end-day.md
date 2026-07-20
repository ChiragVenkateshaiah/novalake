---
description: End-of-day wrap-up — summarize today's progress, then check git branch/status before signing off
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(git fetch:*), Bash(git stash list:*), Read, Glob
---

Close out a work session on NovaLake with a short wrap-up. Do the following, in order, then summarize — do not commit, push, stage, stash, or otherwise change repo state; this command reports and recommends only.

1. **Today's task** — if this session already discussed what was planned for today (e.g. it followed a `/start-day` briefing or an explicit plan earlier in this conversation), summarize progress against that specific task. If no such context exists in this conversation, do not invent or infer a "planned task" that was never actually stated — fall back to reporting only what git shows in step 2.
2. **Git evidence of today's work** — run `git log --oneline --since=midnight` for commits made today, and `git diff --stat` + `git diff --cached --stat` for unstaged/staged changes still outstanding.
3. **Git state for sign-off** — run `git fetch --quiet` (read-only, just updates remote-tracking refs) so the next check is accurate, then `git status -sb` for current branch, ahead/behind `origin/main`, and untracked files. Also run `git stash list` and flag any entries — a forgotten stash is unbacked-up work. If the current branch is `main` and there are any commits since midnight or uncommitted/staged changes, call that out explicitly (this repo's convention is branch-per-module; work on `main` outside a release tag is a hazard, not just a naming nitpick). Otherwise, note whether the branch matches the `feat/vX.Y-phase` convention for whatever phase is in progress (check README's roadmap/status if unclear).
4. **Definition of Done check** — glob `docs/*.md` to see which phase docs exist. If today's work plausibly completes a module (per CONTRIBUTING.md's DoD checklist), note which DoD boxes look satisfied vs. outstanding, based only on what's evidenced by git log/diff and doc file presence — don't guess at things you can't see.

Then give a concise wrap-up (not a wall of text):
- What got done today (from conversation context and/or git log) — or "no commits today" if git shows none
- Outstanding uncommitted/unstaged/stashed work, if any, and the risk of leaving it (none of it is backed up to origin)
- Current branch, ahead/behind `origin/main`, and the on-`main` warning if it applies
- A suggested commit message for outstanding work, if there is any worth committing — suggest only, never run
- DoD status if a module looks close to done, otherwise skip this bullet
- One line suggesting where tomorrow's `/start-day` will likely pick up

End with the wrap-up. Do not commit, stage, push, stash, or modify any files — just report so the user can decide what to do before closing out.
