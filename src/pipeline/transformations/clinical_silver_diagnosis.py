"""clinical_silver.diagnosis: coded ICD-10 diagnoses per encounter, with condition group."""

from pyspark.sql import functions as F

from readmit.pipeline.cdc import register_scd1_table
from readmit.pipeline.clinical_exprs import condition_group
from readmit.pipeline.keys import hash_key
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821

register_scd1_table(
    spark,  # noqa: F821
    settings,
    entity="diagnosis",
    target=settings.table("clinical_silver", "diagnosis"),
    keys=["diagnosis_id"],
    columns=[
        hash_key("encounter_number", "icd10_code", "dx_sequence").alias("diagnosis_id"),
        hash_key("encounter_number").alias("encounter_id"),
        "icd10_code",
        "dx_sequence",
        (F.col("dx_type") == "PRIMARY").alias("is_primary"),
        condition_group(F.col("icd10_code")).alias("condition_group"),
    ],
    schema=(
        "diagnosis_id STRING NOT NULL, encounter_id STRING NOT NULL, icd10_code STRING NOT NULL, "
        "dx_sequence INT NOT NULL, is_primary BOOLEAN NOT NULL, condition_group STRING, "
        "CONSTRAINT diagnosis_pk PRIMARY KEY (diagnosis_id)"
    ),
    comment="ICD-10 diagnoses per encounter. PK = SHA-256(encounter_number, icd10_code, dx_sequence).",
    cluster_by=["encounter_id"],
)
