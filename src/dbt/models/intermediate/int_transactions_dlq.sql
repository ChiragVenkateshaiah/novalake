-- Quarantine: rows with a null / epoch-zero (1970) / far-future (2099)
-- event_timestamp. Complementary filter to int_transactions_clean.sql --
-- together they're exhaustive and exclusive over int_transactions.
select * from {{ ref('int_transactions') }}
where event_timestamp_quality != 'ok'
