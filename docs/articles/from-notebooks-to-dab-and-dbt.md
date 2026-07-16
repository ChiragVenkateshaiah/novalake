# The confidently wrong fix: what building a lakehouse with an AI pair caught, and what it didn't

I've spent years in Databricks notebooks. This week I rebuilt part of my
NovaLake project the way I'd actually want it to run in production — and I did it
with an AI coding assistant as a pair. The most useful thing that happened wasn't
the code it wrote. It was the moment the AI-driven process produced a fix that
was confidently, textbook-correct — and completely wrong for the platform I was
on. A real run caught it. Reasoning didn't.

That's the story I want to tell, because it's the actual lesson, for AI and for
humans both: verification beats confidence.

## The decision I made

NovaLake is a hands-on lakehouse project: deliberately messy synthetic payments
data — polymorphic event types, schema drift between versions, a field that's
sometimes a struct and sometimes a string, replayed IDs — flowing through a
medallion architecture. My original plan built everything as hand-written
notebooks and deferred any deployment tooling to much later.

I decided to reverse that. I wanted the more industry-standard shape: **PySpark
for Bronze**, where Spark genuinely earns its place on nested, malformed JSON;
**dbt for Silver and Gold**, because SQL models with tests and version control are
the software-development layer that notebooks never quite give you; **Genie** for
natural-language serving; and **Databricks Asset Bundles (DAB)** as the deployment
wrapper that turns all of it into a reviewable, reproducible job.

This directly contradicted a decision I'd pinned in my own docs months earlier —
one I'd explicitly written down so it wouldn't get re-litigated by accident. So
when the AI flagged the conflict instead of quietly going along with my new
request, that was exactly right. I confirmed it as a deliberate reversal, not
drift, and we recorded it as one. The architecture calls were mine. The AI's job
was to propose options at the forks and execute under direction — with real
checkpoints.

## The checkpoints mattered

A few of those checkpoints are worth naming, because they're the difference
between "AI wrote my infra" and "I built my infra with AI help."

Before any code got written, I had a second, stronger model review the plan. It
caught real problems on paper: it correctly flagged that a serverless Spark task
needs an explicit compute environment block the draft had assumed it didn't need
— which turned out to be exactly right when we deployed. It also flagged that one
of my choices (was I *dropping* Declarative Pipelines, or *deferring* it?) was a
scope decision the AI shouldn't assume on my behalf. It asked. I chose: deferred
to a later comparative phase, not dropped. That's a fork a human should own, and
the process was built to surface it rather than paper over it.

When I opened the pull request, I opened it as a **draft** — deliberately — and
kept it a draft until the real job had actually run green. Not "the YAML parses."
Not "the plan looks sound." The job ran end-to-end against real serverless
compute first. Only then did it become ready for review.

## What running things for real actually caught

Here's where confidence and reality parted ways, three times.

The cheap check — the bundle's static validation — caught one thing: a second
task also needed its own environment declaration on serverless. Fine. That's what
static validation is for.

Running dbt locally against the real warehouse caught the next: the auth type
Databricks reports as a literal string isn't the literal string dbt accepts, even
though both point at the exact same cached credential. No YAML review would have
found that. You have to actually connect.

Then the first real end-to-end job run **failed** — exit code 127, "command not
found." It's tempting to assume a managed dbt task on Databricks means everything
"just works." The auth part did work; that was never the problem. What doesn't
come for free is dbt itself — serverless compute doesn't ship it preinstalled,
and it has to be declared as an explicit dependency. You find that by running the
job, not by reading the config. Fixed it, reran, got a clean success, and the row
counts matched end to end.

## The confidently wrong fix

And then the best moment. Before merging, I ran a broad automated code review —
multiple agents looking at correctness, simplification, efficiency, conventions.
It found six genuinely good issues, and I fixed them: a diagram that had gone
stale after a config change, a value that only worked by coincidence, a fragile
hardcoded ID that should have been a lookup. Real improvements.

One suggestion was to add `.cache()` before a `count()` in the PySpark ingest, to
avoid re-reading the source. If you know Spark, you know this is *the* idiomatic
move. It's the advice you'd give in an interview. It's correct — on a normal
cluster.

The very next real run failed instantly: serverless Databricks doesn't support
`.cache()` or `.persist()` at all. Spark Connect under the hood simply forecloses
it. The review had applied a general best practice without knowing this specific
platform's limitation, and produced advice that was confident, reasonable, and
wrong. It got caught for one reason only: I re-ran the job instead of trusting the
reasoning. Reverted in seconds. The tiny double-read stays — it costs nothing at
this data size.

That's the whole point. An AI review applying sound general principles can be
confidently wrong about your specific runtime. So can a smart human reviewer. The
thing that told the difference wasn't a better argument — it was an actual
execution.

## What I'd take from this

Using an AI assistant well didn't mean handing over judgment. It meant using it
to move fast on the mechanical work, while keeping the decisions, the checkpoints,
and — most of all — the verification firmly in the loop. The AI proposed and
executed. I decided and verified. And when the process itself produced a polished,
plausible mistake, the discipline of running things for real is what caught it.

I merged that PR as a normal merge commit, not a squash, on purpose — the failed
runs and the reverted fix are still visible in the history. The debugging journey
is the valuable part. Hiding it would throw away the actual lesson.

If there's one thing to carry out of this: validation catches syntax, local runs
catch integration, and only real end-to-end runs catch what the platform actually
does. That's true whether the code was written by you or by your very capable,
occasionally-and-confidently-wrong AI pair.

The repo, decisions, and full debugging notes are public on my GitHub under
NovaLake if you want to see the actual files.
