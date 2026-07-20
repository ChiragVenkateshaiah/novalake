---
description: Morning briefing — repo status, git state, what's next, and standing decisions to keep in mind
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(git fetch:*), Read, Glob
---

Kick off a work session on NovaLake with a short status briefing. Do the following, in order, then summarize — do not start implementing anything yet, and do not propose a plan for today's work.

1. **Git state** — run `git fetch --quiet` (network, read-only — just updates remote-tracking refs), then `git status -sb` and `git log --oneline -8`. Note: current branch, any uncommitted/staged changes, and ahead/behind vs. `origin/main`.
2. **Project status** — read `README.md`'s `Status` and `Roadmap` sections to determine the current phase and what's shipped vs. not, and identify the next unstarted phase.
3. **Phase docs** — glob `docs/*.md` for `NN-phase.md` files and compare against the roadmap table to confirm which phase is actively in progress vs. not yet started. If the next unstarted phase has no `docs/NN-phase.md` of its own yet, also read `docs/plan.md` for any still-relevant plan/outcome notes for that specific phase (skip plan.md entirely once a phase has its own doc — don't read it out of habit).
4. **Pinned decisions** — read the `Status` line and `Re-open at` trigger in `docs/checkpoint.md`. Skim `docs/adr/README.md`'s index and surface only Accepted ADRs relevant to the current/next phase (and flag if any relevant one has been Superseded) — don't dump the whole index.
5. **Definition of Done** — pull the DoD checklist from `CONTRIBUTING.md` so it's front of mind.

Then give a concise briefing (not a wall of text):
- Current phase & status
- Git state: branch, uncommitted work if any, ahead/behind `origin/main`, and — if the current branch doesn't match the next phase's expected `feat/vX.Y-phase` convention — say what that expected branch name would be
- What's next, per the roadmap, plus plan.md notes only if step 3 surfaced them
- Any pinned decision/re-open trigger relevant right now
- DoD checklist reminder (just the bullet list, no elaboration)

End with the briefing. Do not propose a plan, enter plan mode, or start writing code — the user decides what to work on from here.
