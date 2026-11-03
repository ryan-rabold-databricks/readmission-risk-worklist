"""Version-controlled seed files (seeds/*.csv), read from the bundle's workspace files.

Seeds are tiny, so they are read on the driver and typed with a DDL schema.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

SEED_SCHEMAS: dict[str, str] = {
    "facility": "facility_id STRING, facility_name STRING, region STRING, bed_count INT, is_active BOOLEAN",
    "risk_tier_policy": (
        "risk_tier STRING, min_score DOUBLE, max_score DOUBLE, outreach_sla_hours INT, "
        "include_in_worklist BOOLEAN, is_active BOOLEAN"
    ),
    "care_team_assignment": (
        "care_manager_email STRING, facility_id STRING, daily_capacity INT, "
        "effective_date DATE, expiration_date DATE"
    ),
}


def read_seed_rows(seeds_path: str, name: str) -> list[dict[str, str | None]]:
    with open(Path(seeds_path) / f"{name}.csv", newline="") as fh:
        return [{k: (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(fh)]


def read_seed(spark: SparkSession, seeds_path: str, name: str) -> DataFrame:
    fields = [f.strip().split(" ", 1) for f in SEED_SCHEMAS[name].split(",")]
    rows = read_seed_rows(seeds_path, name)
    as_strings = spark.createDataFrame(
        [tuple(r[col] for col, _ in fields) for r in rows],
        ", ".join(f"{col} STRING" for col, _ in fields),
    )
    return as_strings.select(*[F.col(col).cast(dtype).alias(col) for col, dtype in fields])
