-- Silver, transactions_clean (v0.7 comparison target -- see docs/adr/0010).
-- One-line filter over transactions, mirroring int_transactions_clean.sql --
-- keeps the drift/DLQ-resolution logic in exactly one place (transactions.sql),
-- not re-derived here.
--
-- Deliberately NOT an EXPECT ... ON VIOLATION DROP ROW constraint: confirmed
-- (documentation + the live scratch-constraint experiment recorded in
-- docs/07-declarative-pipelines.md) that dropped-row content is not
-- recoverable from the DLT pipeline event log -- only aggregate violation
-- counts are. A manual flag-and-split (this WHERE-based pair) is the only way
-- to keep an inspectable DLQ in either tool; DLT doesn't have a cleaner
-- primitive for this specific need.
CREATE OR REFRESH MATERIALIZED VIEW novalake.silver_dlt.transactions_clean
AS
SELECT * FROM novalake.silver_dlt.transactions
WHERE event_timestamp_quality = 'ok';
