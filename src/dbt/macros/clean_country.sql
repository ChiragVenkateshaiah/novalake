{#
  Dirty categorical requiring alias mapping, not just case/trim. Mapping
  verified against the generator's actual COUNTRIES list
  (data/generators/generate_events.py and generate_multiline.py, identical
  pools): US/USA/United States -> US, GB/uk -> GB, IN/India -> IN,
  CA/Canada -> CA; JP/DE/FR pass through unchanged; null stays null.

  Lifted verbatim from int_transactions.sql's original inline logic -- not
  rewritten, just relocated, to avoid introducing a behavior change.
#}
{% macro clean_country(column) %}
    case
        when {{ column }} is null then null
        when upper(trim({{ column }})) in ('US', 'USA', 'UNITED STATES') then 'US'
        when upper(trim({{ column }})) in ('GB', 'UK') then 'GB'
        when upper(trim({{ column }})) in ('IN', 'INDIA') then 'IN'
        when upper(trim({{ column }})) in ('CA', 'CANADA') then 'CA'
        else upper(trim({{ column }}))
    end
{% endmacro %}
