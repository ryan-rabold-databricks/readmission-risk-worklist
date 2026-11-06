"""readmission_worklist_gold.readmission_outcome: one row per inpatient discharge with
what the program did and what happened.

- Every discharge in discharge_features, including those before go-live (the baseline)
  and LOW-tier discharges that never reach the worklist.
- risk_tier / risk_score: the worklist item's if the discharge was on the worklist,
  otherwise its latest score (NULL before the first model was scored).
- was_reached: the care manager spoke with the patient (REACHED, FOLLOWUP_BOOKED, or
  DECLINED in care_management_silver.outreach_activity); first_contact_hours runs
  from the worklist release (care_worklist.created_at) to that first contact.
- followup_completed_7d / readmitted_30d / readmit_encounter_id come from
  discharge_features; outcome_status is PENDING until the 30-day label matures.

care_worklist and discharge_risk_score are written by the daily cycle's jobs, so this
view reflects the worklists built before the current pipeline update.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from readmit.pipeline.audit import AUDIT_SCHEMA, refresh_audit_columns
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821

CONTACT_TYPES = ("REACHED", "FOLLOWUP_BOOKED", "DECLINED")


@dp.materialized_view(
    name=settings.table("readmission_worklist_gold", "readmission_outcome"),
    comment=(
        "One row per inpatient discharge: risk tier, whether it was on the worklist and the patient "
        "was reached, time to first contact, 7-day follow-up, and the 30-day readmission outcome. "
        "Source for readmission_program_metrics, the app's Program tab, and Genie."
    ),
    schema=(
        "encounter_id STRING NOT NULL, worklist_item_id STRING, facility_id STRING NOT NULL, "
        "discharge_date DATE NOT NULL, primary_condition_group STRING NOT NULL, "
        "risk_tier STRING, risk_score DOUBLE, was_on_worklist BOOLEAN NOT NULL, worklist_date DATE, "
        "assignment_status STRING, attempt_count INT NOT NULL, was_reached BOOLEAN NOT NULL, "
        "first_contact_hours DOUBLE, followup_completed_7d BOOLEAN NOT NULL, readmitted_30d BOOLEAN, "
        "readmit_encounter_id STRING, outcome_status STRING NOT NULL, "
        f"{AUDIT_SCHEMA}, "
        "CONSTRAINT readmission_outcome_pk PRIMARY KEY (encounter_id)"
    ),
    cluster_by=["facility_id", "discharge_date"],
)
@dp.expect_all({
    "reached_only_on_worklist": "NOT was_reached OR was_on_worklist",
    "pending_until_matured": "(outcome_status = 'PENDING') = (readmitted_30d IS NULL)",
})
def readmission_outcome():
    read = spark.read.table  # noqa: F821
    features = read(settings.table("readmission_worklist_gold", "discharge_features"))
    worklist = read(settings.table("readmission_worklist_gold", "care_worklist")).select(
        "encounter_id", "worklist_item_id", "worklist_date", "assignment_status", "created_at",
        F.col("risk_tier").alias("w_risk_tier"), F.col("risk_score").alias("w_risk_score"),
    )
    latest_score = Window.partitionBy("encounter_id").orderBy(F.desc("scored_at"))
    scores = (
        read(settings.table("readmission_worklist_gold", "discharge_risk_score"))
        .withColumn("_rn", F.row_number().over(latest_score))
        .filter("_rn = 1")
        .select("encounter_id", F.col("risk_tier").alias("s_risk_tier"), F.col("risk_score").alias("s_risk_score"))
    )
    outreach = (
        read(settings.table("care_management_silver", "outreach_activity"))
        .groupBy("worklist_item_id")
        .agg(
            F.count("*").cast("int").alias("attempt_count"),
            F.min(F.when(F.col("activity_type").isin(*CONTACT_TYPES), F.col("activity_ts"))).alias("first_contact_ts"),
        )
    )
    reached = F.col("first_contact_ts").isNotNull()
    return (
        features.join(worklist, "encounter_id", "left")
        .join(scores, "encounter_id", "left")
        .join(outreach, "worklist_item_id", "left")
        .select(
            "encounter_id",
            "worklist_item_id",
            "facility_id",
            "discharge_date",
            "primary_condition_group",
            F.coalesce("w_risk_tier", "s_risk_tier").alias("risk_tier"),
            F.coalesce("w_risk_score", "s_risk_score").alias("risk_score"),
            F.col("worklist_item_id").isNotNull().alias("was_on_worklist"),
            "worklist_date",
            "assignment_status",
            F.coalesce("attempt_count", F.lit(0)).alias("attempt_count"),
            reached.alias("was_reached"),
            F.when(reached, (F.unix_timestamp("first_contact_ts") - F.unix_timestamp("created_at")) / 3600.0)
            .alias("first_contact_hours"),
            F.col("followup_within_7d").alias("followup_completed_7d"),
            F.col("readmit_30d").alias("readmitted_30d"),
            "readmit_encounter_id",
            F.when(F.col("readmit_30d").isNull(), "PENDING")
            .when(F.col("readmit_30d"), "READMITTED")
            .otherwise("NOT_READMITTED")
            .alias("outcome_status"),
            *refresh_audit_columns(
                settings.pipeline_name,
                F.col("audit_updated_run_id"),
                created_at=F.col("audit_created_at"),
                created_by=F.col("audit_created_by"),
                created_process=F.col("audit_created_process"),
                created_run_id=F.col("audit_created_run_id"),
            ),
        )
    )
