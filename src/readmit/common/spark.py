"""Spark session helper that works in Databricks jobs and locally via Databricks Connect."""

from __future__ import annotations

import os

from pyspark.sql import SparkSession


def get_spark() -> SparkSession:
    if "DATABRICKS_RUNTIME_VERSION" in os.environ:
        spark = SparkSession.builder.getOrCreate()
    else:
        # Local development: serverless Databricks Connect, profile from
        # DATABRICKS_CONFIG_PROFILE.
        from databricks.connect import DatabricksSession

        spark = DatabricksSession.builder.serverless(True).getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    return spark
