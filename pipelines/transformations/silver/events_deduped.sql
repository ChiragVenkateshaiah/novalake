-- Silver, events_deduped -- Experiment 1 (v0.7 comparison target -- see
-- docs/adr/0010). Mirrors int_events_deduped.sql's generic dedup + envelope-
-- drift resolution (timestamp unification, source struct-vs-flat-string,
-- customer_id/cust_id coalesce), reused across all v0.2 event families in the
-- dbt original but scoped here to whatever flows through this pipeline
-- (transaction.* only, per docs/adr/0010).
--
-- LIVE RESULT (Experiment 1, resolved): attempted first as a STREAMING TABLE,
-- matching the DLT skill's own documented dedup example (ROW_NUMBER() OVER
-- (PARTITION BY ...) ... FROM STREAM ... WHERE rn=1) -- not pre-decided as
-- impossible. DLT REJECTED it outright on deploy:
--   [NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING] Window function is not
--   supported in ROW_NUMBER() (as column `rn`) on streaming DataFrames/
--   Datasets. Structured Streaming only supports time-window aggregation
--   using the WINDOW function.
-- This resolves the conflict the plan flagged between the DLT skill's own
-- canonical example and the general Spark Structured Streaming rule that
-- non-time-bounded ranking windows aren't valid on streaming DataFrames --
-- live behavior sides with the general rule; the skill's example does not
-- hold for this construction. Falls back to MATERIALIZED VIEW here, which
-- cascades to every downstream file in this directory needing a plain
-- (non-STREAM) read of this table rather than STREAM(). See
-- docs/07-declarative-pipelines.md for the full write-up.
CREATE OR REFRESH MATERIALIZED VIEW novalake.silver_dlt.events_deduped
AS
WITH projected AS (
  -- stg_raw_events's exact 10-column allow-list, folded in here rather than
  -- a separate table -- keeps _rescued_data and any other Auto-Loader-added
  -- columns from ever reaching Silver.
  SELECT event_id, event_type, schema_version, event_timestamp, ingested_at,
         source, source_system, payload, _source_file, _ingested_at
  FROM novalake.bronze_dlt.raw_events
),
deduped AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY event_id
      -- ingested_at is a string; cast to timestamp before ordering -- raw
      -- string comparison is unsafe when ISO fractional-second width varies.
      ORDER BY try_cast(ingested_at AS timestamp) DESC, _ingested_at DESC
    ) AS rn
  FROM projected
),
resolved AS (
  SELECT
    event_id,
    event_type,
    schema_version,
    ingested_at,
    event_timestamp,
    -- Envelope timestamp drift: v1 = epoch millis, v2 = ISO-8601 string, both
    -- delivered under the same JSON key -- unify to one TIMESTAMP column. No
    -- ELSE branch: an unrecognized schema_version deliberately yields NULL,
    -- routing the row to the 'null' DLQ bucket below.
    CASE
      WHEN event_timestamp IS NULL THEN NULL
      WHEN schema_version = '1.0' THEN timestamp_millis(try_cast(event_timestamp AS bigint))
      WHEN schema_version = '2.0' THEN try_cast(event_timestamp AS timestamp)
    END AS resolved_event_timestamp,
    -- Source drift: v1 flat string `source_system`, v2 struct `source`.
    CASE WHEN schema_version = '2.0' THEN source.system ELSE source_system END AS resolved_source_system,
    CASE WHEN schema_version = '2.0' THEN source.region ELSE NULL END AS resolved_source_region,
    CASE WHEN schema_version = '2.0' THEN source.host ELSE NULL END AS resolved_source_host,
    -- Key renaming (v1 cust_id vs v2 customer_id) -- both exist as nullable
    -- siblings in the inferred payload struct; exactly one is populated per
    -- row, except payout.scheduled (no customer key -- resolves to NULL, not
    -- relevant to this pipeline's transaction.*-only scope but preserved for
    -- fidelity to the dbt original).
    coalesce(payload.customer_id, payload.cust_id) AS customer_id_resolved,
    payload,
    _source_file,
    _ingested_at
  FROM deduped
  WHERE rn = 1
)
SELECT
  event_id,
  event_type,
  schema_version,
  ingested_at,
  event_timestamp,
  resolved_event_timestamp,
  -- Flags the 3 sentinel values the generator injects on purpose (null /
  -- epoch-zero 1970-01-01 / far-future 2099-12-31), compared against the
  -- RESOLVED timestamp -- comparing the raw column would miss v1-encoded
  -- sentinels (delivered as epoch-millis ints, not ISO strings).
  CASE
    WHEN resolved_event_timestamp IS NULL THEN 'null'
    WHEN resolved_event_timestamp = timestamp('1970-01-01T00:00:00Z') THEN 'epoch_zero'
    WHEN resolved_event_timestamp = timestamp('2099-12-31T00:00:00Z') THEN 'far_future'
    ELSE 'ok'
  END AS event_timestamp_quality,
  resolved_source_system,
  resolved_source_region,
  resolved_source_host,
  customer_id_resolved,
  payload,
  _source_file,
  _ingested_at
FROM resolved;
