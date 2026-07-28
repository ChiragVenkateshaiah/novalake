{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Override dbt's default "<target_schema>_<custom>" concatenation so
        +schema: silver resolves to exactly novalake.silver, not
        novalake.silver_silver / novalake.<target>_silver. -#}
    {%- if custom_schema_name is none -%}
        {%- set base = target.schema -%}
    {%- else -%}
        {%- set base = custom_schema_name | trim -%}
    {%- endif -%}
    {#- v0.9 (docs/adr/0011-gb-scale-data-regeneration.md): append a _gb
        suffix when building against the GB-scale parallel schemas
        (bronze_gb/silver_gb/gold_gb), so every existing model runs
        unmodified against either scale depending on this one var. Only
        resolves from CLI --vars (see dbt_project.yml's materialization
        block for the same constraint) -- the inline `false` default is
        what keeps the unflagged path unchanged. -#}
    {{- base ~ ('_gb' if var('is_gb_scale', false) else '') -}}
{%- endmacro %}
