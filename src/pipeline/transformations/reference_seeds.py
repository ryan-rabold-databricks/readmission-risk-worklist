"""Reference tables loaded from version-controlled seed files (seeds/*.csv).

- clinical_silver.facility
- care_management_silver.risk_tier_policy
- care_management_silver.care_team_assignment

Phase 4 adds Program Settings changes (Lakebase CDF) on top of the seeded values.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from readmit.pipeline.audit import AUDIT_SCHEMA, refresh_audit_columns
from readmit.pipeline.keys import hash_key
from readmit.pipeline.seeds import read_seed
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821
c = settings.catalog


def _audit(seed: str):
    return refresh_audit_columns(settings.pipeline_name, F.lit(f"seed:{seed}.csv"))


@dp.materialized_view(
    name=settings.table("clinical_silver", "facility"),
    comment="Facilities in the health system (seed: seeds/facility.csv).",
    schema=(
        "facility_id STRING NOT NULL, facility_name STRING NOT NULL, region STRING NOT NULL, "
        f"bed_count INT, is_active BOOLEAN NOT NULL, {AUDIT_SCHEMA}, "
        "CONSTRAINT facility_pk PRIMARY KEY (facility_id)"
    ),
)
def facility():
    return read_seed(spark, settings.seeds_path, "facility").select("*", *_audit("facility"))  # noqa: F821


@dp.materialized_view(
    name=settings.table("care_management_silver", "risk_tier_policy"),
    comment="Risk tier cut-offs and outreach SLAs (seed: seeds/risk_tier_policy.csv).",
    schema=(
        "risk_tier STRING NOT NULL, min_score DOUBLE NOT NULL, max_score DOUBLE NOT NULL, "
        "outreach_sla_hours INT NOT NULL, include_in_worklist BOOLEAN NOT NULL, "
        f"is_active BOOLEAN NOT NULL, {AUDIT_SCHEMA}, "
        "CONSTRAINT risk_tier_policy_pk PRIMARY KEY (risk_tier)"
    ),
)
@dp.expect_all_or_fail({"score_range_valid": "min_score >= 0 AND max_score <= 1 AND min_score < max_score"})
def risk_tier_policy():
    return read_seed(spark, settings.seeds_path, "risk_tier_policy").select("*", *_audit("risk_tier_policy"))  # noqa: F821


@dp.materialized_view(
    name=settings.table("care_management_silver", "care_team_assignment"),
    comment=(
        "Care manager to facility assignments and daily capacity (seed: "
        "seeds/care_team_assignment.csv). PK = SHA-256(care_manager_email, facility_id)."
    ),
    schema=(
        "assignment_id STRING NOT NULL, care_manager_email STRING NOT NULL, facility_id STRING NOT NULL, "
        "daily_capacity INT NOT NULL, effective_date DATE NOT NULL, expiration_date DATE, "
        f"{AUDIT_SCHEMA}, "
        "CONSTRAINT care_team_assignment_pk PRIMARY KEY (assignment_id), "
        f"CONSTRAINT care_team_assignment_facility_fk FOREIGN KEY (facility_id) REFERENCES {c}.clinical_silver.facility (facility_id)"
    ),
)
@dp.expect_all_or_fail({"capacity_positive": "daily_capacity > 0"})
def care_team_assignment():
    seed = read_seed(spark, settings.seeds_path, "care_team_assignment")  # noqa: F821
    return seed.select(
        hash_key(F.lower("care_manager_email"), "facility_id").alias("assignment_id"),
        F.lower("care_manager_email").alias("care_manager_email"),
        "facility_id", "daily_capacity", "effective_date", "expiration_date",
        *_audit("care_team_assignment"),
    )
