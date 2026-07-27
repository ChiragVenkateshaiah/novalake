-- Bronze, raw_events (v0.7 comparison target -- see docs/adr/0010). DLT-side
-- Bronze, parallel to novalake.bronze.raw_events (dbt/PySpark ingest path) --
-- not a replacement. ndjson source only, per docs/adr/0010's Silver-only scope.
--
-- LIVE FINDING, corrects the original plan's assumption: STREAM read_files()
-- rejects a bare literal file path outright with "Input path ... is not a
-- directory" -- Auto Loader's streaming listener requires the path to
-- resolve as a directory (with an optional glob filter), even when the
-- target is a single, unambiguous file. Pointing at the landing folder
-- directly would also silently ingest the sibling
-- payments_events_multiline.json (a different, non-ndjson layout) as
-- garbage rows. Fix: a one-character bracket class `[.]` around the literal
-- dot before the extension -- functionally an exact match on
-- "payments_events.json" (no other file can satisfy it) but syntactically
-- contains glob metacharacters, so Auto Loader resolves the parent as a
-- directory-with-filter instead of rejecting a literal file path.
--
-- schemaHints pins payload.risk/payload.amount_minor/event_timestamp/
-- ingested_at to STRING because the dbt chain's from_json/try_cast logic
-- downstream only works because the *original* batch spark.read.json() call
-- happened to infer all four as STRING (risk is a JSON object ~97% of the
-- time, a literal string ~3%; amount_minor is an int ~90%, string ~10%;
-- event_timestamp/ingested_at are epoch-millis ints in schema v1, ISO strings
-- in v2, both under the same JSON key). Auto Loader's sample-based inference
-- isn't guaranteed to land the same way -- getting any of these wrong would
-- either hard-fail from_json/try_cast or silently rescue the minority-typed
-- rows into _rescued_data, nulling their resolved value while the row count
-- still matched. If a future _rescued_data check (see
-- pipelines/transformations/../../docs/07-declarative-pipelines.md) ever
-- shows a nonzero count for a column not hinted here, `DESCRIBE
-- novalake.bronze.raw_events` (the known-good batch inference) is the
-- authoritative source for the correct hint, not guessing further columns.
CREATE OR REFRESH STREAMING TABLE novalake.bronze_dlt.raw_events (
  CONSTRAINT has_event_id EXPECT (event_id IS NOT NULL)
)
COMMENT 'Raw polymorphic event envelope, ndjson source only. DLT-side Bronze, parallel to novalake.bronze.raw_events (dbt path) -- not a replacement.'
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '/Volumes/${novalake.catalog}/bronze/landing/payments_events[.]json',
  format => 'json',
  inferColumnTypes => 'true',
  schemaHints => 'payload.risk STRING, payload.amount_minor STRING, event_timestamp STRING, ingested_at STRING'
);
