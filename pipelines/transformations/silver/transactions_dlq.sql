-- Silver, transactions_dlq (v0.7 comparison target -- see docs/adr/0010).
-- Quarantine: rows with a null / epoch-zero (1970) / far-future (2099)
-- event_timestamp, mirroring int_transactions_dlq.sql. Complementary filter
-- to transactions_clean.sql -- together they're exhaustive and exclusive
-- over transactions. See transactions_clean.sql for why this is a
-- WHERE-split rather than an EXPECT ... ON VIOLATION DROP ROW constraint.
CREATE OR REFRESH MATERIALIZED VIEW novalake.silver_dlt.transactions_dlq
AS
SELECT * FROM novalake.silver_dlt.transactions
WHERE event_timestamp_quality != 'ok';
