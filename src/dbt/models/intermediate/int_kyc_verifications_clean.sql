select * from {{ ref('int_kyc_verifications') }}
where event_timestamp_quality = 'ok'
