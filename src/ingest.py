"""PySpark Bronze ingest: land payments_events.json into novalake.bronze.raw_events.

Job-driven counterpart to notebooks/01_bronze/01_bronze_raw_event_ingestion.ipynb
(the original hand-run v0.1 notebook, left in place as the historical record).
Same behavior: schema-on-read, no restructuring, no type fixes — that's Silver's
job (now dbt's, see src/dbt/).

Follow-up not solved here: this is a full-overwrite batch load, safe for a
one-time/re-run load but not how a recurring scheduled job should behave
long-term. Incremental/idempotent loading (Auto Loader or COPY INTO) is real
follow-up work, flagged and deferred, not forgotten.
"""

import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="novalake")
    args = parser.parse_args()

    catalog = args.catalog
    raw_path = f"/Volumes/{catalog}/bronze/landing/payments_events.json"

    spark = SparkSession.builder.getOrCreate()

    df_inferred = spark.read.json(raw_path)

    bronze_df = (
        df_inferred
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_ingested_at", F.current_timestamp())
    )

    (bronze_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{catalog}.bronze.raw_events"))

    print(f"Wrote {bronze_df.count()} rows to {catalog}.bronze.raw_events")


if __name__ == "__main__":
    main()
