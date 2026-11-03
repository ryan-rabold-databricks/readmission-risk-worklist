"""clinical_silver.follow_up_appointment: post-discharge appointments and their status.

booked_ts is when the appointment was first booked (source record creation), which is
what the scoring model may use: a follow-up booked at discharge is known the morning
after; whether the patient attended is not.
"""

from pyspark.sql import functions as F

from readmit.pipeline.cdc import register_scd1_table
from readmit.pipeline.keys import hash_key
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821

register_scd1_table(
    spark,  # noqa: F821
    settings,
    entity="appointment",
    target=settings.table("clinical_silver", "follow_up_appointment"),
    keys=["appointment_id"],
    columns=[
        hash_key("appointment_number").alias("appointment_id"),
        hash_key("mrn").alias("patient_id"),
        hash_key("source_encounter_number").alias("source_encounter_id"),
        "scheduled_ts",
        "provider_type",
        "status",
        F.col("record_created_ts").alias("booked_ts"),
    ],
    schema=(
        "appointment_id STRING NOT NULL, patient_id STRING NOT NULL, source_encounter_id STRING, "
        "scheduled_ts TIMESTAMP NOT NULL, provider_type STRING NOT NULL, status STRING NOT NULL, "
        "booked_ts TIMESTAMP NOT NULL, "
        "CONSTRAINT follow_up_appointment_pk PRIMARY KEY (appointment_id)"
    ),
    comment="Follow-up appointments booked at discharge. PK = SHA-256(appointment_number).",
    cluster_by=["source_encounter_id"],
)
