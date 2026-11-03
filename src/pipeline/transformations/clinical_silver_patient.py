"""clinical_silver.patient: current demographics per patient (AUTO CDC from patient_raw)."""

from pyspark.sql import functions as F

from readmit.pipeline.cdc import register_scd1_table
from readmit.pipeline.keys import hash_key
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821
patient = settings.table("clinical_silver", "patient")

register_scd1_table(
    spark,  # noqa: F821
    settings,
    entity="patient",
    target=patient,
    keys=["patient_id"],
    columns=[
        hash_key("mrn").alias("patient_id"),
        "mrn", "first_name", "last_name", "birth_date", "sex", "phone", "zip_code", "primary_payer",
    ],
    schema=(
        "patient_id STRING NOT NULL, mrn STRING NOT NULL, first_name STRING NOT NULL, "
        "last_name STRING NOT NULL, birth_date DATE NOT NULL, sex STRING, phone STRING, "
        "zip_code STRING, primary_payer STRING NOT NULL, "
        "CONSTRAINT patient_pk PRIMARY KEY (patient_id)"
    ),
    comment="Current patient demographics from the EHR. PK patient_id = SHA-256(mrn).",
    cluster_by=["patient_id"],
)
