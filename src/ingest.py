"""PySpark Bronze ingest: land payments_events.json into novalake.bronze.raw_events.

Job-driven counterpart to notebooks/01_bronze/01_bronze_raw_event_ingestion.ipynb
(the original hand-run v0.1 notebook, left in place as the historical record).
Same behavior: schema-on-read, no restructuring, no type fixes — that's Silver's
job (now dbt's, see src/dbt/).

Follow-up not solved here: this is a full-overwrite batch load, safe for a
one-time/re-run load but not how a recurring scheduled job should behave
long-term. Incremental/idempotent loading (Auto Loader or COPY INTO) is real
follow-up work, flagged and deferred, not forgotten.

v0.9 (docs/adr/0011-gb-scale-data-regeneration.md): --raw-path/--target-schema
let this same script also land the GB-scale parallel dataset into
bronze_gb.raw_events, without changing the default (unflagged) small-scale
path at all. --verbose-count gates the extra full-table count() pass behind
an opt-in flag for the GB path -- a real cost at tens of millions of rows,
not the tiny thing it is at ~7K.
"""

import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="novalake")
    parser.add_argument(
        "--raw-path", default=None,
        help="Override the source path (default: /Volumes/{catalog}/bronze/landing/payments_events.json).",
    )
    parser.add_argument(
        "--target-schema", default="bronze",
        help="UC schema to write to (default: bronze; use bronze_gb for the v0.9 GB-scale path).",
    )
    parser.add_argument(
        "--verbose-count", action=argparse.BooleanOptionalAction, default=True,
        help="Print the written row count via an extra count() pass (default: on, matching "
             "original behavior). Pass --no-verbose-count for the GB-scale path -- a full "
             "extra pass over tens of millions of rows is real cost, not the tiny thing it "
             "is at ~7K rows.",
    )
    args = parser.parse_args()

    catalog = args.catalog
    raw_path = args.raw_path or f"/Volumes/{catalog}/bronze/landing/payments_events.json"
    target_table = f"{catalog}.{args.target_schema}.raw_events"

    spark = SparkSession.builder.getOrCreate()

    df_inferred = spark.read.json(raw_path)

    bronze_df = (
        df_inferred
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_ingested_at", F.current_timestamp())
    )
    # No .cache() here: Databricks serverless compute does not support
    # persist()/cache() (confirmed the hard way — job failed with
    # NOT_SUPPORTED_WITH_SERVERLESS).

    (bronze_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(target_table))

    if args.verbose_count:
        print(f"Wrote {bronze_df.count()} rows to {target_table}")
    else:
        print(f"Wrote to {target_table}")


if __name__ == "__main__":
    main()
