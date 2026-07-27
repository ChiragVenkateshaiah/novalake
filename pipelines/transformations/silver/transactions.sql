-- Silver, transactions (v0.7 comparison target -- see docs/adr/0010). Mirrors
-- int_transactions.sql's payload-drift resolution, scoped to
-- transaction.{completed,failed,created}. Expected to look nearly identical
-- to the dbt original -- a deliberate negative result for this phase's
-- write-up, not a place to force a difference that isn't there.
--
-- Materialized view rather than streaming: reads events_deduped as a plain
-- (non-STREAM) source regardless of whether Experiment 1 (events_deduped.sql)
-- landed as a streaming table or a materialized view -- this table has no
-- streaming-specific logic of its own to test.
--
-- Dedup-correctness note: dbt's schema tests enforce unique+not_null on
-- int_transactions.event_id -- the one test that actually validates the
-- upstream dedup step, not just downstream drift-resolution logic. EXPECT
-- cannot express row-uniqueness across a table (no non-scalar per-row
-- expression at this scope) -- a genuine DLT capability gap, documented in
-- docs/07-declarative-pipelines.md rather than worked around here. Row-count
-- parity against events_deduped (7,000 dbt = 7,000 DLT) is this pipeline's
-- indirect substitute check.
CREATE OR REFRESH MATERIALIZED VIEW novalake.silver_dlt.transactions (
  CONSTRAINT customer_id_present EXPECT (customer_id_resolved IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT amount_present EXPECT (amount_minor_resolved IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT risk_score_present EXPECT (risk_score IS NOT NULL) ON VIOLATION FAIL UPDATE,
  -- Mirrors int_transactions_clean.sql's implicit guarantee (only 'ok'-quality
  -- rows flow to _clean) -- scoped the same way here since DLT has no
  -- separate _clean-only model to attach the not_null test to.
  CONSTRAINT resolved_ts_present_when_ok EXPECT (
    resolved_event_timestamp IS NOT NULL OR event_timestamp_quality != 'ok'
  ) ON VIOLATION FAIL UPDATE,
  -- Warn-only (no ON VIOLATION clause -- DLT's documented default action),
  -- the direct analog to dbt's severity: warn accepted_values test. 90 real
  -- "US$" rows (data/generators/generate_events.py's CURRENCIES_DIRTY),
  -- confirmed live, are a known, intentionally-injected bad value that
  -- should surface, not fail the pipeline.
  CONSTRAINT currency_known EXPECT (currency_clean IN ('USD','EUR','GBP','INR','JPY','CAD','AUD'))
)
AS
WITH risk_parsed AS (
  SELECT
    *,
    from_json(payload.risk, 'score double, flagged boolean, reasons array<string>') AS risk_struct
  FROM novalake.silver_dlt.events_deduped
  WHERE event_type IN ('transaction.completed', 'transaction.failed', 'transaction.created')
)
SELECT
  event_id,
  event_type,
  schema_version,
  resolved_event_timestamp,
  event_timestamp_quality,
  resolved_source_system,
  resolved_source_region,
  resolved_source_host,

  -- Key renaming (v1 cust_id vs v2 customer_id) resolved generically in
  -- events_deduped -- not re-derived here.
  customer_id_resolved,

  -- Unit + type drift: v1 `amount` (major-unit float, always populated), v2
  -- `amount_minor` (minor-unit int, always populated, ~10% delivered as a
  -- string -- try_cast handles both underlying types safely).
  CASE
    WHEN schema_version = '2.0' THEN try_cast(payload.amount_minor AS bigint)
    WHEN schema_version = '1.0' THEN try_cast(round(payload.amount * 100) AS bigint)
  END AS amount_minor_resolved,

  -- Dirty categorical: casing/whitespace recover via upper+trim.
  -- clean_currency macro inlined verbatim -- "US$" is the one genuinely
  -- invalid CURRENCIES_DIRTY value and will NOT match a clean code, kept
  -- visible via currency_clean, not silently discarded (see the warn
  -- constraint above).
  payload.currency AS currency_raw,
  upper(trim(payload.currency)) AS currency_clean,

  -- Dirty categorical requiring alias mapping, not just case/trim.
  -- clean_country macro inlined verbatim -- mapping verified against the
  -- generator's actual COUNTRIES list.
  payload.country AS country_raw,
  CASE
    WHEN payload.country IS NULL THEN NULL
    WHEN upper(trim(payload.country)) IN ('US', 'USA', 'UNITED STATES') THEN 'US'
    WHEN upper(trim(payload.country)) IN ('GB', 'UK') THEN 'GB'
    WHEN upper(trim(payload.country)) IN ('IN', 'INDIA') THEN 'IN'
    WHEN upper(trim(payload.country)) IN ('CA', 'CANADA') THEN 'CA'
    ELSE upper(trim(payload.country))
  END AS country_clean,

  -- risk: struct collapsed to STRING at Bronze for ALL rows (well-formed
  -- rows are valid JSON *text*, the ~3% malformed rows are literal "score=X"
  -- text) -- recover via from_json for the well-formed rows, regex fallback
  -- for the malformed ones.
  coalesce(
    risk_struct.score,
    try_cast(regexp_extract(payload.risk, 'score=([0-9]+\\.[0-9]+)', 1) AS double)
  ) AS risk_score,
  risk_struct.flagged AS risk_flagged,   -- null for malformed rows: never recoverable from the string
  risk_struct.reasons AS risk_reasons,   -- null for malformed rows: never recoverable from the string
  risk_struct.score IS NULL AS risk_malformed,  -- score is never null in well-formed rows

  payload.merchant AS merchant,
  payload.payment_method AS payment_method,
  payload.status AS status,
  payload.idempotency_key AS idempotency_key,
  payload.line_items AS line_items,     -- untouched; no explode step in this pipeline's scope

  _source_file,
  _ingested_at
FROM risk_parsed;
