# Contributing / Working Conventions

This is a solo learning project, but run with real engineering hygiene — partly
because the discipline is the point, partly because this repo is also a portfolio
artifact.

## Branching
- `main` is always the last known-good state.
- One branch per module: `feat/v0.1-bronze`, `feat/v0.2-silver`, etc.
- Merge to `main` only when that module's Definition of Done (below) is met.

## Commits
[Conventional Commits](https://www.conventionalcommits.org/):
```
feat(silver): explode line_items and flatten payment_method struct
fix(bronze): correct rescued-data column name in ingest notebook
docs(v0.2): fill validation + knowledge check sections
```

## Tags / Releases
Tag `main` at the end of each module: `v0.0`, `v0.1`, `v0.2`, … Tag message =
one-line summary of what now works.

## Definition of Done (per module)
- [ ] Table(s)/asset(s) created and queryable
- [ ] Logic committed under the layer's actual home: `src/ingest.py` (Bronze),
      `src/dbt/models/<layer>/` (Silver/Gold, with dbt tests passing — those count
      toward "validation checklist is green" the same as a manual check would),
      `resources/` (DAB job/task definitions), or `notebooks/<phase>/` for
      historical/exploratory work not promoted to a script
- [ ] `docs/<NN>-<phase>.md` filled in — sections 1–9 at minimum, not just headers
- [ ] Validation checklist in that doc is green
- [ ] Tagged release pushed

## Raw data policy
Raw JSON payloads are **not** committed to Git — they live in
`novalake.bronze.landing` (a Unity Catalog Volume). Only the generator scripts
(`data/generators/`) and data dictionaries (`data/dictionaries/`) are version
controlled, so the data is always reproducible without bloating the repo.

## Notebooks
- Path: `notebooks/<phase>/<NN>_<description>.py`
- One logical transformation per notebook where reasonable; prefer several small,
  readable notebooks over one large one.
- Markdown cells explain *why*, not just *what* — this repo is meant to be readable
  by someone other than its author.
