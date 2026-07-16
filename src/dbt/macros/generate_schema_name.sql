{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Override dbt's default "<target_schema>_<custom>" concatenation so
        +schema: silver resolves to exactly novalake.silver, not
        novalake.silver_silver / novalake.<target>_silver. -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
