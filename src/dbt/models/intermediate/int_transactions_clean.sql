-- One-line filter over int_transactions -- keeps the drift/DLQ-resolution
-- logic in exactly one place (int_transactions.sql), not re-derived here.
select * from {{ ref('int_transactions') }}
where event_timestamp_quality = 'ok'
