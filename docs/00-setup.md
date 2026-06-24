# Module 0 · Project & Environment Setup

`Status:` In progress  ·  `Owner:` Chirag  ·  `Last updated:` _TBD_  ·  `Est. time:` ~45 min

## 1. Learning Objectives
- [ ] Can explain the Unity Catalog hierarchy: metastore → catalog → schema → table/volume
- [ ] Can connect a Databricks workspace to a GitHub repo via Git folders and explain
      what a Git folder actually syncs
- [ ] Have a working catalog + four layer schemas + one landing volume, created
      idempotently from a notebook (not by hand-clicking, so it's repeatable)

## 2. Prerequisites
- None — this is the first module.

## 3. Where This Fits (Architecture Context)
This module produces no data, only the *places* later data will live: the
`novalake` catalog, one schema per medallion layer, and the landing volume that
Bronze reads from. Everything from `v0.1` onward targets these objects by name.

```
novalake (catalog)
├── bronze   (schema)  → landing (volume)   ← raw files uploaded here
├── silver   (schema)
├── gold     (schema)
└── serving  (schema)
```
`genai` schema is intentionally not created yet — added in `v0.7`, only when needed.

## 4. Concepts & Background
- **Metastore / Catalog / Schema / Volume** — Unity Catalog's three-level namespace
  (`catalog.schema.object`); a Volume is UC's governed way of storing arbitrary
  files (as opposed to tables) — this is where raw JSON lands before Bronze reads it.
- **Workspace catalog vs. a created catalog** — Free Edition provisions a default
  workspace catalog automatically; we create a dedicated `novalake` catalog instead,
  on the same logic a real team would use a separate catalog per project/domain.
- **Git folder** — a Git-backed folder inside the Databricks workspace; notebooks
  committed here are real files in the GitHub repo, not workspace-only objects.
- **Idempotent setup** — every DDL statement in the setup notebook uses
  `IF NOT EXISTS` so re-running it is always safe. Worth internalizing early:
  this same idea reappears constantly in Bronze/Silver (`MERGE`, `CREATE OR REPLACE`).

## 5. Conventions Established (project-wide, not just this module)
- **Naming:** `novalake.<layer>.<object>` — e.g. `novalake.bronze.transactions_raw`
- **Layer schemas:** `bronze`, `silver`, `gold`, `serving` (+ `genai` from v0.7)
- **Notebook path/naming:** `notebooks/<phase>/<NN>_<description>.py`,
  e.g. `notebooks/02_silver/01_explode_events.py`
- **Doc status tags:** `Draft` → `In progress` → `Validated`
- **Raw data lives in the Volume, not in Git** — only generator code and data
  guides are version-controlled (`data/generators/`, `data/dictionaries/`);
  the actual JSON payloads are uploaded straight to `novalake.bronze.landing`.

## 6. Step-by-Step Implementation

- **Step 6.1 — Create the GitHub repo**
  - *Task:* Create `novalake` on GitHub, push this scaffold.
  - *Status:* ⬜ pending

- **Step 6.2 — Link GitHub to the Databricks workspace**
  - *Task:* Settings → Linked accounts → Git credential (OAuth or PAT).
  - *Status:* ⬜ pending

- **Step 6.3 — Clone as a Git folder**
  - *Task:* Workspace → Create → Git folder → paste the repo URL.
  - *Status:* ⬜ pending

- **Step 6.4 — Run `notebooks/00_setup/01_catalog_schema_volume.py`**
  - *Task:* Create catalog, 4 schemas, landing volume.
  - *Expected output:* `SHOW SCHEMAS IN novalake` returns 4 rows.
  - *Status:* ⬜ pending

- **Step 6.5 — Upload both datasets to the landing volume**
  - *Task:* `payments_events.json` and `payments_events_multiline.json` →
    `/Volumes/novalake/bronze/landing/`.
  - *Status:* ⬜ pending

## 7. Operational Considerations
- Re-running the setup notebook is safe (idempotent DDL) — useful if Free Edition
  ever resets compute/session state.

## 8. Data Quality & Governance
- N/A this module — no data has landed yet. Ownership: catalog/schemas owned by
  the workspace admin (you, on Free Edition).

## 9. Validation & Acceptance Criteria
- [x] `SHOW CATALOGS` includes `novalake`
- [x] `SHOW SCHEMAS IN novalake` returns `bronze, silver, gold, serving`
- [x] `SHOW VOLUMES IN novalake.bronze` returns `landing`
- [x] Both raw files visible under `/Volumes/novalake/bronze/landing/`
- [x] Git folder shows clean status against `main` in the Databricks UI

## 10. Key Takeaways
- Free Edition gives you full workspace-admin rights on your own metastore - `CREATE CATALOG` worked directly, no fallback to an existing default catalog needed.
- Unity Catalog Volumes are the governed landing zone for files-as-files; tables come later, in Bronze - the volume itself stores zero schema.
- The 5,296,607 / 8,086,444 byte sizes matched the generator's output exactly, confirming a clean upload with no truncation.

## 11. Knowledge Check
- Q1: Why a Volume and not just `dbfs:/FileStore` for the raw files?
- Q2: What's the actual difference between the workspace's default catalog and
  the `novalake` catalog we created?

## 12. References
- Internal: `docs/checkpoint.md`, `docs/_skeleton.md`
- Databricks docs: Unity Catalog volumes, Git folders setup

## Changelog
| Date | Change | Author |
|------|--------|--------|
| _TBD_ | Module created | Chirag + Claude |
