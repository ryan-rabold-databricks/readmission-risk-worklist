"""Reading the app's Lakebase CDF history (readmission_worklist_app_bronze.lb_*_history).

Each history row is one Postgres change: ``_pg_change_type`` (insert, update_preimage,
update_postimage, delete), ordered by (``_pg_lsn``, ``_sort_by``). Postgres UUIDs land
as 16-byte BINARY (DECISIONS.md #43); silver stores them as canonical UUID strings so
they match the IDs the app sees in Postgres.
"""

from __future__ import annotations

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from readmit.pipeline.program_settings import Change

APP_BRONZE = "readmission_worklist_app_bronze"
CHANGE_TYPES = ("insert", "update_postimage", "delete")
APP_PROCESS = "readmission_worklist_app"


def uuid_from_binary(col: str | Column) -> Column:
    """16-byte BINARY -> 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' (lowercase)."""
    h = F.lower(F.hex(F.col(col) if isinstance(col, str) else col))
    return F.concat_ws("-", F.substring(h, 1, 8), F.substring(h, 9, 4), F.substring(h, 13, 4),
                       F.substring(h, 17, 4), F.substring(h, 21, 12))


def history_table(catalog: str, app_table: str) -> str:
    return f"{catalog}.{APP_BRONZE}.lb_{app_table}_history"


def sequence() -> Column:
    return F.struct("_pg_lsn", "_sort_by")


def current_state(history: DataFrame, key: str) -> DataFrame:
    """Latest change per key, with deleted rows removed (batch read of the history)."""
    latest = Window.partitionBy(key).orderBy(F.desc("_pg_lsn"), F.desc("_sort_by"))
    return (
        history.filter(F.col("_pg_change_type").isin(*CHANGE_TYPES))
        .withColumn("_rn", F.row_number().over(latest))
        .filter((F.col("_rn") == 1) & (F.col("_pg_change_type") != "delete"))
        .drop("_rn")
    )


def program_setting_changes(spark: SparkSession, catalog: str) -> list[Change]:
    """Current Program Settings changes, oldest first. The history table is created by
    the Lakebase CDF feed (<env>_readmit_setup), which must run before the pipeline;
    the SDP runtime blocks catalog existence checks, so a missing table fails loudly."""
    rows = (
        current_state(spark.read.table(history_table(catalog, "program_setting_change")), "change_id")
        .select(uuid_from_binary("change_id").alias("change_id"), "setting_type", "target_key",
                "new_value_json", "effective_date", "changed_by", "changed_at")
        .orderBy("changed_at", "change_id")
        .collect()
    )
    return [Change(r.change_id, r.setting_type, r.target_key, r.new_value_json, r.effective_date,
                   r.changed_by, r.changed_at) for r in rows]
