"""Reference tables loaded from version-controlled seed files (seeds/*.csv).

- clinical_silver.facility
- care_management_silver.risk_tier_policy
- care_management_silver.care_team_assignment
- care_management_silver.care_manager_capacity

The three care-management tables are effective-dated: the seeds plus every Program
Settings change the pipeline applied (readmit.pipeline.program_settings). Rows from a
change carry it in audit_created_* (by = changed_by, run_id = change_id); seed rows
carry the seed file. care_management_silver.program_setting lists every change with
its validation result.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from readmit.pipeline import program_settings as ps
from readmit.pipeline.app_changes import APP_PROCESS, program_setting_changes
from readmit.pipeline.audit import AUDIT_SCHEMA, refresh_audit_columns
from readmit.pipeline.keys import hash_key
from readmit.pipeline.seeds import SEED_SCHEMAS, read_seed
from readmit.pipeline.settings import load_settings

settings = load_settings(spark)  # noqa: F821


def _audit(seed: str):
    return refresh_audit_columns(settings.pipeline_name, F.lit(f"seed:{seed}.csv"))


def _validated_changes() -> list[ps.Validated]:
    facilities = {r.facility_id for r in read_seed(spark, settings.seeds_path, "facility").collect()}  # noqa: F821
    return ps.validate_all(program_setting_changes(spark, settings.catalog), facilities)  # noqa: F821


def _versioned(seed: str, apply, row_ddl: str):
    """Seed rows plus applied changes as a DataFrame of ``row_ddl`` columns plus change
    provenance, with audit columns describing the seed file or the change."""
    base = [r.asDict() for r in read_seed(spark, settings.seeds_path, seed).collect()]  # noqa: F821
    changes = _validated_changes()
    by_id = {v.change.change_id: v.change for v in changes}
    cols = [c.strip().split(" ", 1)[0] for c in row_ddl.split(",")]
    rows = []
    for r in apply(base, changes):
        c = by_id.get(r["change_id"])
        rows.append((*[r.get(k) for k in cols], r["change_id"], c.changed_by if c else None, c.changed_at if c else None))
    df = spark.createDataFrame(  # noqa: F821
        rows, f"{row_ddl}, _change_id STRING, _changed_by STRING, _changed_at TIMESTAMP"
    )
    from_change = F.col("_change_id").isNotNull()
    seed_run = F.lit(f"seed:{seed}.csv")
    return df.select(
        *cols,
        *refresh_audit_columns(
            settings.pipeline_name,
            seed_run,
            created_at=F.when(from_change, F.col("_changed_at")).otherwise(F.current_timestamp()),
            created_by=F.when(from_change, F.col("_changed_by")).otherwise(F.expr("current_user()")),
            created_process=F.when(from_change, F.lit(APP_PROCESS)).otherwise(F.lit(settings.pipeline_name)),
            created_run_id=F.when(from_change, F.col("_change_id")).otherwise(seed_run),
        ),
    )


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
    comment=(
        "Risk tier cut-offs and outreach SLAs, effective-dated (seed: seeds/risk_tier_policy.csv, "
        "plus applied Program Settings changes). Scoring and worklist builds use the version "
        "active on the worklist date."
    ),
    schema=(
        "risk_tier STRING NOT NULL, min_score DOUBLE NOT NULL, max_score DOUBLE NOT NULL, "
        "outreach_sla_hours INT NOT NULL, include_in_worklist BOOLEAN NOT NULL, "
        "is_active BOOLEAN NOT NULL, effective_date DATE NOT NULL, expiration_date DATE, "
        f"{AUDIT_SCHEMA}, "
        "CONSTRAINT risk_tier_policy_pk PRIMARY KEY (risk_tier, effective_date)"
    ),
)
@dp.expect_all_or_fail({
    "score_range_valid": "min_score >= 0 AND max_score <= 1 AND min_score < max_score",
    "dates_ordered": "expiration_date IS NULL OR expiration_date > effective_date",
})
def risk_tier_policy():
    return _versioned("risk_tier_policy", ps.tier_policy_rows, SEED_SCHEMAS["risk_tier_policy"])


@dp.materialized_view(
    name=settings.table("care_management_silver", "care_team_assignment"),
    comment=(
        "Facilities each care manager covers, effective-dated (seed: seeds/care_team_assignment.csv, "
        "plus applied Program Settings changes). PK = SHA-256(care_manager_email, facility_id, effective_date)."
    ),
    schema=(
        "assignment_id STRING NOT NULL, care_manager_email STRING NOT NULL, facility_id STRING NOT NULL, "
        f"effective_date DATE NOT NULL, expiration_date DATE, {AUDIT_SCHEMA}, "
        "CONSTRAINT care_team_assignment_pk PRIMARY KEY (assignment_id)"
    ),
)
@dp.expect_all_or_fail({"dates_ordered": "expiration_date IS NULL OR expiration_date > effective_date"})
def care_team_assignment():
    df = _versioned("care_team_assignment", _lower_emails(ps.assignment_rows), SEED_SCHEMAS["care_team_assignment"])
    return df.select(
        hash_key("care_manager_email", "facility_id", "effective_date").alias("assignment_id"), "*"
    )


@dp.materialized_view(
    name=settings.table("care_management_silver", "care_manager_capacity"),
    comment=(
        "Daily capacity per care manager: the most new worklist items assigned to them per day, "
        "across all their facilities, effective-dated (seed: seeds/care_manager_capacity.csv, plus "
        "applied Program Settings changes). PK = SHA-256(care_manager_email, effective_date)."
    ),
    schema=(
        "capacity_id STRING NOT NULL, care_manager_email STRING NOT NULL, daily_capacity INT NOT NULL, "
        f"effective_date DATE NOT NULL, expiration_date DATE, {AUDIT_SCHEMA}, "
        "CONSTRAINT care_manager_capacity_pk PRIMARY KEY (capacity_id)"
    ),
)
@dp.expect_all_or_fail({
    "capacity_positive": "daily_capacity > 0",
    "dates_ordered": "expiration_date IS NULL OR expiration_date > effective_date",
})
def care_manager_capacity():
    df = _versioned("care_manager_capacity", _lower_emails(ps.capacity_rows), SEED_SCHEMAS["care_manager_capacity"])
    return df.select(hash_key("care_manager_email", "effective_date").alias("capacity_id"), "*")


def _lower_emails(apply):
    """Seed emails are matched case-insensitively; app changes are already lowercase."""
    def wrapped(base, changes):
        return apply([dict(r, care_manager_email=r["care_manager_email"].lower()) for r in base], changes)
    return wrapped


@dp.materialized_view(
    name=settings.table("care_management_silver", "program_setting"),
    comment=(
        "Every Program Settings change made in the app (Lakebase CDF, current state), with the "
        "pipeline's validation result: APPLIED, SUPERSEDED (a later change for the same key and "
        "effective_date), or REJECTED (status_reason says why). PK = change_id (Postgres UUID)."
    ),
    schema=(
        "change_id STRING NOT NULL, setting_type STRING NOT NULL, target_key STRING NOT NULL, "
        "new_value_json STRING NOT NULL, effective_date DATE NOT NULL, changed_by STRING NOT NULL, "
        "changed_at TIMESTAMP NOT NULL, status STRING NOT NULL, status_reason STRING, "
        f"{AUDIT_SCHEMA}, "
        "CONSTRAINT program_setting_pk PRIMARY KEY (change_id)"
    ),
)
def program_setting():
    rows = [
        (v.change.change_id, v.change.setting_type, v.change.target_key, v.change.new_value_json,
         v.change.effective_date, v.change.changed_by, v.change.changed_at, v.status, v.status_reason)
        for v in _validated_changes()
    ]
    df = spark.createDataFrame(  # noqa: F821
        rows,
        "change_id STRING, setting_type STRING, target_key STRING, new_value_json STRING, effective_date DATE, "
        "changed_by STRING, changed_at TIMESTAMP, status STRING, status_reason STRING",
    )
    return df.select(
        "*",
        *refresh_audit_columns(
            settings.pipeline_name,
            F.lit("lakebase_cdf"),
            created_at=F.col("changed_at"),
            created_by=F.col("changed_by"),
            created_process=F.lit(APP_PROCESS),
            created_run_id=F.col("change_id"),
        ),
    )
