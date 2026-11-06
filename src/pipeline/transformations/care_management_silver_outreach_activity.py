"""care_management_silver.outreach_activity: care-manager outreach logged in the app.

Source: Lakebase readmission_worklist_app.outreach_activity, landed by Lakebase CDF as
readmission_worklist_app_bronze.lb_outreach_activity_history (one row per Postgres
change). AUTO CDC (SCD Type 1) keeps the current state: changes apply in (_pg_lsn,
_sort_by) order and deletes remove the row (the app can only insert; deletes come from
the demo outreach simulator's reconcile). activity_id arrives as BINARY and is stored
as the canonical UUID string the app sees in Postgres (DECISIONS.md #43).
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from readmit.pipeline.app_changes import APP_PROCESS, CHANGE_TYPES, history_table, sequence, uuid_from_binary
from readmit.pipeline.audit import AUDIT_SCHEMA
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821

TARGET = settings.table("care_management_silver", "outreach_activity")


@dp.temporary_view(name="outreach_activity_changes")
def outreach_activity_changes():
    return (
        spark.readStream.table(history_table(settings.catalog, "outreach_activity"))  # noqa: F821
        .filter(F.col("_pg_change_type").isin(*CHANGE_TYPES))
        .select(
            uuid_from_binary("activity_id").alias("activity_id"),
            "worklist_item_id",
            "client_request_id",
            F.lower("care_manager_email").alias("care_manager_email"),
            "activity_type",
            "activity_ts",
            "next_step_due_at",
            "note",
            F.col("created_at").alias("audit_created_at"),
            F.lower("care_manager_email").alias("audit_created_by"),
            F.lit(APP_PROCESS).alias("audit_created_process"),
            F.col("client_request_id").alias("audit_created_run_id"),
            F.current_timestamp().alias("audit_updated_at"),
            F.expr("current_user()").alias("audit_updated_by"),
            F.lit(settings.pipeline_name).alias("audit_updated_process"),
            F.concat(F.lit("lakebase_cdf_lsn_"), F.col("_pg_lsn").cast("string")).alias("audit_updated_run_id"),
            "_pg_change_type",
            sequence().alias("_seq"),
        )
    )


dp.create_streaming_table(
    name=TARGET,
    comment=(
        "Outreach calls logged by care managers in the app (current state of the Lakebase CDF history). "
        "PK = activity_id (Postgres UUID); client_request_id is unique per app request."
    ),
    schema=(
        "activity_id STRING NOT NULL, worklist_item_id STRING NOT NULL, client_request_id STRING NOT NULL, "
        "care_manager_email STRING NOT NULL, activity_type STRING NOT NULL, activity_ts TIMESTAMP NOT NULL, "
        "next_step_due_at TIMESTAMP, note STRING, "
        f"{AUDIT_SCHEMA}, "
        "CONSTRAINT outreach_activity_pk PRIMARY KEY (activity_id)"
    ),
    cluster_by=["worklist_item_id"],
)

dp.create_auto_cdc_flow(
    target=TARGET,
    source="outreach_activity_changes",
    keys=["activity_id"],
    sequence_by="_seq",
    apply_as_deletes=F.expr("_pg_change_type = 'delete'"),
    except_column_list=["_pg_change_type", "_seq"],
    stored_as_scd_type=1,
)
