"""Audit columns carried by every silver and gold table (DECISIONS.md #22).

- Source-derived tables (AUTO CDC): audit_created_* describe the source record's
  creation (record_created_ts from the EHR); audit_updated_* describe the extract and
  pipeline that applied the latest change.
- Seed and gold tables (recomputed): audit_created_* carry the upstream record's
  creation where there is one; audit_updated_* describe the latest refresh.
"""

from __future__ import annotations

from pyspark.sql import Column
from pyspark.sql import functions as F

AUDIT_SCHEMA = (
    "audit_created_at TIMESTAMP NOT NULL, audit_created_by STRING NOT NULL, "
    "audit_created_process STRING NOT NULL, audit_created_run_id STRING NOT NULL, "
    "audit_updated_at TIMESTAMP NOT NULL, audit_updated_by STRING NOT NULL, "
    "audit_updated_process STRING NOT NULL, audit_updated_run_id STRING NOT NULL"
)


def _extract_run(d: Column) -> Column:
    return F.concat(F.lit("ehr_extract_"), d.cast("string"))


def source_audit_columns(pipeline_name: str) -> list[Column]:
    return [
        F.col("record_created_ts").alias("audit_created_at"),
        F.lit("ehr").alias("audit_created_by"),
        F.lit("ehr_extract").alias("audit_created_process"),
        _extract_run(F.to_date("record_created_ts")).alias("audit_created_run_id"),
        F.current_timestamp().alias("audit_updated_at"),
        F.expr("current_user()").alias("audit_updated_by"),
        F.lit(pipeline_name).alias("audit_updated_process"),
        _extract_run(F.col("extract_date")).alias("audit_updated_run_id"),
    ]


def refresh_audit_columns(
    pipeline_name: str,
    run_id: Column,
    created_at: Column | None = None,
    created_by: Column | None = None,
    created_process: Column | None = None,
    created_run_id: Column | None = None,
) -> list[Column]:
    now = F.current_timestamp()
    who = F.expr("current_user()")
    process = F.lit(pipeline_name)
    return [
        (created_at if created_at is not None else now).alias("audit_created_at"),
        (created_by if created_by is not None else who).alias("audit_created_by"),
        (created_process if created_process is not None else process).alias("audit_created_process"),
        (created_run_id if created_run_id is not None else run_id).alias("audit_created_run_id"),
        now.alias("audit_updated_at"),
        who.alias("audit_updated_by"),
        process.alias("audit_updated_process"),
        run_id.alias("audit_updated_run_id"),
    ]
