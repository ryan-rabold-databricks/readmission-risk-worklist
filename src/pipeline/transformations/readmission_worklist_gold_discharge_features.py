"""readmission_worklist_gold.discharge_features: one row per inpatient discharge.

Model inputs are known the morning after discharge (LACE-style features plus whether
a follow-up within 7 days was booked by then). Outcome columns are filled in later:
- followup_within_7d: the patient attended a follow-up within 7 days (outcome only,
  never a model input, DECISIONS.md #23).
- readmit_30d: unplanned (non-elective) inpatient admission within 30 days of
  discharge; NULL until the 30-day window has passed in the data (label_matured_at).
Hospice discharges are excluded, as in CMS HRRP.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from readmit.pipeline.audit import AUDIT_SCHEMA, refresh_audit_columns
from readmit.pipeline.clinical_exprs import charlson_flag_aggs, charlson_index
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821

LOOKBACK_ED_DAYS = 182
LOOKBACK_INPATIENT_DAYS = 365
FOLLOWUP_WINDOW_DAYS = 7
FOLLOWUP_BOOKED_WITHIN_HOURS = 24  # booked by the morning-after scoring run
WORKLIST_RELEASE_HOUR_UTC = 12  # readmit.common.dates.release_ts
READMIT_WINDOW_DAYS = 30


def _days(n: int):
    return F.expr(f"INTERVAL {n} DAYS")


@dp.materialized_view(
    name=settings.table("readmission_worklist_gold", "discharge_features"),
    comment=(
        "Inpatient discharges with model features (known at scoring time) and outcomes "
        "(followup_within_7d, readmit_30d label, label_matured_at)."
    ),
    schema=(
        "encounter_id STRING NOT NULL, patient_id STRING NOT NULL, facility_id STRING NOT NULL, "
        "discharge_date DATE NOT NULL, age_at_discharge INT NOT NULL, length_of_stay_days INT NOT NULL, "
        "emergent_admission BOOLEAN NOT NULL, charlson_index INT NOT NULL, ed_visits_6m INT NOT NULL, "
        "inpatient_admits_12m INT NOT NULL, primary_condition_group STRING NOT NULL, discharge_disposition STRING, "
        "followup_scheduled_7d BOOLEAN NOT NULL, followup_within_7d BOOLEAN NOT NULL, "
        f"readmit_30d BOOLEAN, label_matured_at TIMESTAMP, {AUDIT_SCHEMA}, "
        "CONSTRAINT discharge_features_pk PRIMARY KEY (encounter_id)"
    ),
    cluster_by=["facility_id", "discharge_date"],
)
# A discharge can arrive before its patient record (late-arriving EHR data). Drop it
# (counted in the event log) rather than fail the refresh; it appears once the record lands.
@dp.expect_or_drop("patient_record_present", "age_at_discharge IS NOT NULL")
@dp.expect_all({
    "age_plausible": "age_at_discharge BETWEEN 18 AND 110",
    "label_only_when_matured": "(readmit_30d IS NULL) = (label_matured_at IS NULL)",
})
def discharge_features():
    read = spark.read.table  # noqa: F821
    encounter = read(settings.table("clinical_silver", "encounter"))
    patient = read(settings.table("clinical_silver", "patient")).select("patient_id", "birth_date")
    diagnosis = read(settings.table("clinical_silver", "diagnosis"))
    appointment = read(settings.table("clinical_silver", "follow_up_appointment"))

    index = encounter.filter(
        (F.col("encounter_type") == "INPATIENT")
        & F.col("discharge_ts").isNotNull()
        & (F.coalesce(F.col("discharge_disposition"), F.lit("")) != "HOSPICE")
    )
    keys = index.select("encounter_id", "patient_id", "admit_ts", "discharge_ts")
    other = encounter.select(
        F.col("patient_id").alias("o_patient_id"),
        F.col("encounter_id").alias("o_encounter_id"),
        F.col("encounter_type").alias("o_type"),
        F.col("admission_type").alias("o_admission_type"),
        F.col("admit_ts").alias("o_admit_ts"),
    )
    same_patient = F.col("patient_id") == F.col("o_patient_id")

    # Prior utilization, strictly before the index admission.
    prior = keys.join(
        other,
        same_patient
        & (F.col("o_admit_ts") < F.col("admit_ts"))
        & (F.col("o_admit_ts") >= F.col("admit_ts") - _days(LOOKBACK_INPATIENT_DAYS)),
    )
    utilization = prior.groupBy("encounter_id").agg(
        F.sum(
            F.when(
                (F.col("o_type") == "ED")
                & (F.col("o_admit_ts") >= F.col("admit_ts") - _days(LOOKBACK_ED_DAYS)),
                1,
            ).otherwise(0)
        ).alias("ed_visits_6m"),
        F.sum(F.when(F.col("o_type") == "INPATIENT", 1).otherwise(0)).alias("inpatient_admits_12m"),
    )

    # Charlson index from the index stay plus encounters in the prior 12 months.
    charlson_scope = keys.select("encounter_id", F.col("encounter_id").alias("dx_encounter_id")).unionByName(
        prior.select("encounter_id", F.col("o_encounter_id").alias("dx_encounter_id"))
    )
    charlson = (
        charlson_scope.join(
            diagnosis.select(F.col("encounter_id").alias("dx_encounter_id"), "icd10_code"), "dx_encounter_id"
        )
        .groupBy("encounter_id")
        .agg(*charlson_flag_aggs(F.col("icd10_code")))
        .select("encounter_id", charlson_index().alias("charlson_index"))
    )

    primary_dx = diagnosis.filter("is_primary").select(
        "encounter_id", F.col("condition_group").alias("primary_condition_group")
    )

    in_window = (F.col("scheduled_ts") > F.col("discharge_ts")) & (
        F.col("scheduled_ts") <= F.col("discharge_ts") + _days(FOLLOWUP_WINDOW_DAYS)
    )
    followup = (
        keys.join(appointment, F.col("encounter_id") == F.col("source_encounter_id"))
        .groupBy("encounter_id")
        .agg(
            F.max(
                in_window
                & (F.col("booked_ts") <= F.col("discharge_ts") + F.expr(f"INTERVAL {FOLLOWUP_BOOKED_WITHIN_HOURS} HOURS"))
                # Known at scoring time only: bookings made after the worklist release
                # (care-manager outreach) are outcomes of the program, not inputs.
                & (F.col("booked_ts") < F.to_timestamp(F.concat(
                    F.date_add(F.to_date("discharge_ts"), 1).cast("string"), F.lit(f" {WORKLIST_RELEASE_HOUR_UTC:02d}:00:00"))))
            ).alias("followup_scheduled_7d"),
            F.max(in_window & (F.col("status") == "COMPLETED")).alias("followup_within_7d"),
        )
    )

    readmitted = (
        keys.join(
            other,
            same_patient
            & (F.col("o_type") == "INPATIENT")
            & (F.coalesce(F.col("o_admission_type"), F.lit("")) != "ELECTIVE")
            & (F.col("o_admit_ts") > F.col("discharge_ts"))
            & (F.col("o_admit_ts") <= F.col("discharge_ts") + _days(READMIT_WINDOW_DAYS)),
        )
        .select("encounter_id")
        .distinct()
        .withColumn("readmitted", F.lit(True))
    )

    # Labels mature against the data, not the wall clock, so reruns are reproducible.
    data_as_of = encounter.agg(
        F.max(F.greatest("admit_ts", F.coalesce("discharge_ts", "admit_ts"))).alias("data_as_of")
    )
    matures_at = F.col("discharge_ts") + _days(READMIT_WINDOW_DAYS)
    matured = matures_at <= F.col("data_as_of")

    return (
        index.join(patient, "patient_id", "left")
        .join(utilization, "encounter_id", "left")
        .join(charlson, "encounter_id", "left")
        .join(primary_dx, "encounter_id", "left")
        .join(followup, "encounter_id", "left")
        .join(readmitted, "encounter_id", "left")
        .crossJoin(data_as_of)
        .select(
            "encounter_id",
            "patient_id",
            "facility_id",
            F.to_date("discharge_ts").alias("discharge_date"),
            F.floor(F.months_between(F.to_date("discharge_ts"), "birth_date") / 12).cast("int").alias("age_at_discharge"),
            "length_of_stay_days",
            F.coalesce(F.col("admission_type").isin("EMERGENCY", "URGENT"), F.lit(False)).alias("emergent_admission"),
            F.coalesce("charlson_index", F.lit(0)).alias("charlson_index"),
            F.coalesce("ed_visits_6m", F.lit(0)).cast("int").alias("ed_visits_6m"),
            F.coalesce("inpatient_admits_12m", F.lit(0)).cast("int").alias("inpatient_admits_12m"),
            # Primary diagnoses outside the mapped condition groups count as "other".
            F.coalesce("primary_condition_group", F.lit("other")).alias("primary_condition_group"),
            "discharge_disposition",
            F.coalesce("followup_scheduled_7d", F.lit(False)).alias("followup_scheduled_7d"),
            F.coalesce("followup_within_7d", F.lit(False)).alias("followup_within_7d"),
            F.when(matured, F.coalesce("readmitted", F.lit(False))).alias("readmit_30d"),
            F.when(matured, matures_at).alias("label_matured_at"),
            *refresh_audit_columns(
                settings.pipeline_name,
                F.concat(F.lit("ehr_extract_"), F.to_date("data_as_of").cast("string")),
                created_at=F.col("audit_created_at"),
                created_by=F.col("audit_created_by"),
                created_process=F.col("audit_created_process"),
                created_run_id=F.col("audit_created_run_id"),
            ),
        )
    )
