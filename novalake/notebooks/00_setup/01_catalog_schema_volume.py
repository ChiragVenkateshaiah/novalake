# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — Catalog, Schemas, Volume
# MAGIC **Module:** `v0.0` · NovaLake
# MAGIC
# MAGIC Creates the Unity Catalog objects every later phase targets:
# MAGIC `novalake` catalog → `bronze` / `silver` / `gold` / `serving` schemas →
# MAGIC a `landing` volume inside `bronze` for the two raw JSON files.
# MAGIC
# MAGIC Safe to re-run — every statement is `IF NOT EXISTS`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parameters

# COMMAND ----------

dbutils.widgets.text("catalog_name", "novalake", "Catalog name")
catalog_name = dbutils.widgets.get("catalog_name")
print(f"Using catalog: {catalog_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Create the catalog
# MAGIC On Free Edition you're the workspace admin of your own metastore, so this should
# MAGIC just work. **If you get a permission error instead:** comment this cell out,
# MAGIC change `catalog_name` above to your workspace's existing default catalog
# MAGIC (Admin Settings → Advanced → "Default catalog for the workspace"), then continue
# MAGIC from Step 2 — schemas/volumes still work fine inside an existing catalog.

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog_name}")
spark.sql(f"USE CATALOG {catalog_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. One schema per medallion layer
# MAGIC `genai` is intentionally NOT created here — it arrives in `v0.7`. Create only
# MAGIC what the current phase needs; resist pre-building the whole tree on day one.

# COMMAND ----------

for schema in ["bronze", "silver", "gold", "serving"]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog_name}.{schema}")
    print(f"  ✓ {catalog_name}.{schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Landing volume
# MAGIC This is where you'll upload `payments_events.json` and
# MAGIC `payments_events_multiline.json` in the next step — the real entry point of Bronze.

# COMMAND ----------

spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog_name}.bronze.landing")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verify

# COMMAND ----------

display(spark.sql(f"SHOW SCHEMAS IN {catalog_name}"))

# COMMAND ----------

display(spark.sql(f"SHOW VOLUMES IN {catalog_name}.bronze"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Next: upload the two datasets
# MAGIC Easiest path on Free Edition: **Catalog Explorer** → `novalake` → `bronze` →
# MAGIC `landing` → **Upload to this volume** → select both `.json` files from your machine.
# MAGIC
# MAGIC Once uploaded, this cell should list both files:

# COMMAND ----------

display(dbutils.fs.ls(f"/Volumes/{catalog_name}/bronze/landing"))
