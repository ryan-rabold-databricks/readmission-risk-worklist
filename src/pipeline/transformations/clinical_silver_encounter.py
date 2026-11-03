"""clinical_silver.encounter: latest state of each inpatient stay and ED visit.

Inpatient stays arrive once at admission (no discharge yet) and again at discharge;
AUTO CDC keeps the latest.
"""

from pyspark.sql import functions as F

from readmit.pipeline.cdc import register_scd1_table
from readmit.pipeline.keys import hash_key
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821

register_scd1_table(
    spark,  # noqa: F821
    settings,
    entity="encounter",
    target=settings.table("clinical_silver", "encounter"),
    keys=["encounter_id"],
    columns=[
        hash_key("encounter_number").alias("encounter_id"),
        "encounter_number",
        hash_key("mrn").alias("patient_id"),
        "facility_id", "encounter_type", "admission_type", "admit_ts", "discharge_ts",
        "discharge_disposition", "drg_code",
        F.when(
            F.col("discharge_ts").isNotNull(),
            F.datediff(F.to_date("discharge_ts"), F.to_date("admit_ts")),
        ).alias("length_of_stay_days"),
    ],
    schema=(
        "encounter_id STRING NOT NULL, encounter_number STRING NOT NULL, patient_id STRING NOT NULL, "
        "facility_id STRING NOT NULL, encounter_type STRING NOT NULL, admission_type STRING, "
        "admit_ts TIMESTAMP NOT NULL, discharge_ts TIMESTAMP, discharge_disposition STRING, "
        "drg_code STRING, length_of_stay_days INT, "
        "CONSTRAINT encounter_pk PRIMARY KEY (encounter_id)"
    ),
    comment="Latest state of each EHR encounter. PK encounter_id = SHA-256(encounter_number).",
    cluster_by=["patient_id"],
)
