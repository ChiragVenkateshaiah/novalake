{#
  Dirty categorical: casing/whitespace recover via upper+trim. "US$" is the
  one genuinely invalid CURRENCIES_DIRTY value (data/generators/
  generate_events.py) and will NOT match a clean code -- kept visible via the
  cleaned output, not silently discarded (see the warn-severity accepted_values
  test wherever this macro's output is tested).

  Lifted verbatim from int_transactions.sql's original inline logic -- not
  rewritten, just relocated, to avoid introducing a behavior change.
#}
{% macro clean_currency(column) %}
    upper(trim({{ column }}))
{% endmacro %}
