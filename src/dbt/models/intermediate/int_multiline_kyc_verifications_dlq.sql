select * from {{ ref('int_multiline_kyc_verifications') }}
where event_timestamp_quality != 'ok'
