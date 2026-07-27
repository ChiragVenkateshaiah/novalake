"""PySpark Bronze ingest: land payments_events_multiline.json into
novalake.bronze.raw_events_multiline.

Companion to src/ingest.py, for the "hard mode" multiline export file --
the whole file is one pretty-printed JSON array (one page document per
element), read with multiLine=true, yielding one row per page (9 rows at
the original small scale). Same principle as src/ingest.py: schema-on-read,
no restructuring, no type fixes, and deliberately no pre-shaping of the
dynamic-key-map fields (metadata, balances, tax_ids, consents, checksums,
currency_catalog, etc.) that data/dictionaries/dataset_guide_multiline.md
calls a "schema-explosion trap" -- Bronze enforces no schema and drops
nothing, same as the NDJSON file; every fix (including reconstructing those
fields as maps) is Silver's job (dbt, see src/dbt/), not Bronze's.

Follow-up not solved here: same full-overwrite batch load caveat as
src/ingest.py.

v0.9 (docs/adr/0011-gb-scale-data-regeneration.md): --raw-path/--target-schema
let this same script land the GB-scale parallel dataset into
bronze_gb.raw_events_multiline. At GB scale the source is a DIRECTORY of many
payments_events_multiline_part_NNNNN.json files (data/generators/generate_multiline.py's
multi-file rewrite), not one literal filename -- Spark's multiLine=true
reader handles a directory of JSON-array files the same way it handles one,
each file still yields one row per page. --verbose-count gates the extra
full-table count() pass, same reasoning as src/ingest.py.
"""

import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="novalake")
    parser.add_argument(
        "--raw-path", default=None,
        help="Override the source path -- a directory for the GB-scale multi-file layout, "
             "a single file for the default small-scale path. Default: "
             "/Volumes/{catalog}/bronze/landing/payments_events_multiline.json.",
    )
    parser.add_argument(
        "--target-schema", default="bronze",
        help="UC schema to write to (default: bronze; use bronze_gb for the v0.9 GB-scale path).",
    )
    parser.add_argument(
        "--verbose-count", action=argparse.BooleanOptionalAction, default=True,
        help="Print the written row count via an extra count() pass (default: on, matching "
             "original behavior). Pass --no-verbose-count for the GB-scale path.",
    )
    args = parser.parse_args()

    catalog = args.catalog
    raw_path = args.raw_path or f"/Volumes/{catalog}/bronze/landing/payments_events_multiline.json"
    target_table = f"{catalog}.{args.target_schema}.raw_events_multiline"

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
        .saveAsTable(target_table))

    if args.verbose_count:
        print(f"Wrote {bronze_df.count()} rows to {target_table}")
    else:
        print(f"Wrote to {target_table}")


if __name__ == "__main__":
    main()
