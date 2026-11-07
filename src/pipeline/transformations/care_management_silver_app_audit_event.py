"""care_management_silver.app_audit_event: business audit events emitted by the app.

Source: Databricks Apps telemetry, readmission_worklist_app_bronze.app_otel_logs, records
from the app's `readmission-worklist.audit` logger (src/app/server/audit.ts) with
attributes `event.name` = `audit.<event>` and `audit.*` fields. Telemetry delivery can
repeat a record, so events are de-duplicated on event_id (AUTO CDC SCD Type 1).
IDs only, never PHI (DECISIONS.md #13). Platform events in the same table (sign-ins,
HTTP requests, stdout) are not business audit events and are left in bronze.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from readmit.pipeline.app_changes import APP_BRONZE, APP_PROCESS
from readmit.pipeline.audit import AUDIT_SCHEMA
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821

TARGET = settings.table("care_management_silver", "app_audit_event")
AUDIT_SCOPE = "readmission-worklist.audit"


def _attr(name: str):
    return F.expr(f"attributes:['{name}']::string")


@dp.temporary_view(name="app_audit_event_changes")
def app_audit_event_changes():
    return (
        spark.readStream.table(f"{settings.catalog}.{APP_BRONZE}.app_otel_logs")  # noqa: F821
        .filter((F.col("instrumentation_scope.name") == AUDIT_SCOPE) & _attr("event.name").startswith("audit."))
        .select(
            _attr("audit.event_id").alias("event_id"),
            F.substring(_attr("event.name"), 7, 100).alias("event_name"),
            F.lower(_attr("audit.user_email")).alias("user_email"),
            _attr("audit.action").alias("action"),
            _attr("audit.record_type").alias("record_type"),
            _attr("audit.record_id").alias("record_id"),
            _attr("audit.facility_id").alias("facility_id"),
            F.nullif(F.col("trace_id"), F.lit("")).alias("trace_id"),
            F.col("time").alias("event_ts"),
            F.current_timestamp().alias("ingested_at"),
            F.col("time").alias("audit_created_at"),
            F.lower(_attr("audit.user_email")).alias("audit_created_by"),
            F.lit(APP_PROCESS).alias("audit_created_process"),
            F.coalesce(F.nullif(F.col("trace_id"), F.lit("")), _attr("audit.event_id")).alias("audit_created_run_id"),
            F.current_timestamp().alias("audit_updated_at"),
            F.expr("current_user()").alias("audit_updated_by"),
            F.lit(settings.pipeline_name).alias("audit_updated_process"),
            F.concat(F.lit("app_otel_logs_"), F.col("date").cast("string")).alias("audit_updated_run_id"),
        )
    )


dp.create_streaming_table(
    name=TARGET,
    comment=(
        "Business audit events from the app (worklist.viewed, outreach.logged, settings.changed, genie.asked), "
        "de-duplicated on event_id from app_otel_logs. IDs only, never PHI."
    ),
    schema=(
        "event_id STRING NOT NULL, event_name STRING NOT NULL, user_email STRING NOT NULL, action STRING NOT NULL, "
        "record_type STRING, record_id STRING, facility_id STRING, trace_id STRING, "
        "event_ts TIMESTAMP NOT NULL, ingested_at TIMESTAMP NOT NULL, "
        f"{AUDIT_SCHEMA}, "
        "CONSTRAINT app_audit_event_pk PRIMARY KEY (event_id)"
    ),
    cluster_by=["event_ts"],
)

dp.create_auto_cdc_flow(
    target=TARGET,
    source="app_audit_event_changes",
    keys=["event_id"],
    sequence_by="event_ts",
    stored_as_scd_type=1,
)
