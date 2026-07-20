"""PySpark Bronze ingest: land payments_events_multiline.json into
novalake.bronze.raw_events_multiline.

Companion to src/ingest.py, for the "hard mode" multiline export file --
the whole file is one pretty-printed JSON array (one page document per
element), read with multiLine=true, yielding one row per page (9 rows
expected). Same principle as src/ingest.py: schema-on-read, no
restructuring, no type fixes, and deliberately no pre-shaping of the
dynamic-key-map fields (metadata, balances, tax_ids, consents, checksums,
currency_catalog, etc.) that data/dictionaries/dataset_guide_multiline.md
calls a "schema-explosion trap" -- Bronze enforces no schema and drops
nothing, same as the NDJSON file; every fix (including reconstructing those
fields as maps) is Silver's job (dbt, see src/dbt/), not Bronze's.

Follow-up not solved here: same full-overwrite batch load caveat as
src/ingest.py.
"""

import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="novalake")
    args = parser.parse_args()

    catalog = args.catalog
    raw_path = f"/Volumes/{catalog}/bronze/landing/payments_events_multiline.json"

    spark = SparkSession.builder.getOrCreate()

    df_inferred = spark.read.option("multiLine", "true").json(raw_path)

    bronze_df = (
        df_inferred
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_ingested_at", F.current_timestamp())
    )
    # No .cache() here -- same serverless constraint as src/ingest.py.

    (bronze_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{catalog}.bronze.raw_events_multiline"))

    print(f"Wrote {bronze_df.count()} rows to {catalog}.bronze.raw_events_multiline")


if __name__ == "__main__":
    main()
