"""Story checks printed at the end of every simulator run (committed as evidence).

The 30-day label mirrors what the pipeline will compute: an index inpatient stay is
readmitted when the same patient has any inpatient admission within 30 days after
discharge. Only labels that have matured by run_date are counted, and hospice
discharges are excluded (as in CMS HRRP).
"""

from __future__ import annotations

from datetime import date, timedelta

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def labeled_stays(inpatient: DataFrame, run_date: date) -> DataFrame:
    stays = inpatient.select(
        "patient_idx", "encounter_number", "facility_id", "condition_group",
        "admit_ts", "discharge_ts", "discharge_disposition",
        (F.col("followup_7d_planned") & ~F.coalesce(
            F.col("readmit_admit_ts") < F.col("scheduled_ts"), F.lit(False)
        )).alias("followup_7d"),
    )
    later = stays.select(
        F.col("patient_idx").alias("p2"), F.col("admit_ts").alias("next_admit_ts")
    )
    readmitted = (
        stays.join(
            later,
            (F.col("patient_idx") == F.col("p2"))
            & (F.col("next_admit_ts") > F.col("discharge_ts"))
            & (F.col("next_admit_ts") <= F.col("discharge_ts") + F.expr("INTERVAL 30 DAYS")),
            "left_semi",
        )
        .select("encounter_number")
        .withColumn("readmit_30d", F.lit(True))
    )
    matured_by = run_date - timedelta(days=30)
    return (
        stays.filter(F.to_date("discharge_ts") <= F.lit(matured_by))
        .filter(F.col("discharge_disposition") != "HOSPICE")
        .join(readmitted, "encounter_number", "left")
        .withColumn("readmit_30d", F.coalesce("readmit_30d", F.lit(False)))
    )


def story_report(inpatient: DataFrame, run_date: date, avg_readmission_cost: float) -> str:
    """Build the report from one fine-grained aggregate (a single Spark action)."""
    cells = [
        r.asDict()
        for r in labeled_stays(inpatient, run_date)
        .withColumn("winter", F.month("discharge_ts").isin(12, 1, 2))
        .groupBy("facility_id", "condition_group", "followup_7d", "winter")
        .agg(F.count("*").alias("stays"), F.sum(F.col("readmit_30d").cast("int")).alias("readmits"))
        .collect()
    ]

    def rollup(key, where=lambda c: True) -> list[tuple]:
        acc: dict = {}
        for c in cells:
            if where(c):
                a = acc.setdefault(key(c), [0, 0, 0])
                a[0] += c["stays"]
                a[1] += c["readmits"]
                a[2] += c["stays"] if c["followup_7d"] else 0
        return sorted((k, *v) for k, v in acc.items())

    def fmt(rows) -> list[str]:
        return [
            f"  {k} | stays={n:,} | readmit_30d={r / n:.1%} | followup_7d={f / n:.1%}"
            for k, n, r, f in rows
        ]

    (_, n, r, f), = rollup(lambda c: "all")
    return "\n".join(
        [
            "== Story checks (matured, non-hospice inpatient stays) ==",
            f"Overall: stays={n:,} readmits={r:,} rate={r / n:.1%} followup_7d={f / n:.1%} "
            f"est_readmission_cost=${r * avg_readmission_cost:,.0f}",
            "By facility:",
            *fmt(rollup(lambda c: c["facility_id"])),
            "By condition group:",
            *fmt(rollup(lambda c: c["condition_group"])),
            "Heart failure by 7-day follow-up:",
            *fmt(rollup(lambda c: f"followup_7d={c['followup_7d']}", lambda c: c["condition_group"] == "heart_failure")),
            "COPD + pneumonia by season:",
            *fmt(rollup(lambda c: f"winter={c['winter']}", lambda c: c["condition_group"] in ("copd", "pneumonia"))),
        ]
    )


def extract_counts(extracts: dict[str, DataFrame]) -> dict[str, dict[str, int]]:
    """Row counts per entity and extract date, in a single Spark action."""
    combined = None
    for entity, df in extracts.items():
        part = df.groupBy("extract_date").count().withColumn("entity", F.lit(entity))
        combined = part if combined is None else combined.unionByName(part)
    counts: dict[str, dict[str, int]] = {entity: {} for entity in extracts}
    for r in combined.collect():
        counts[r["entity"]][r["extract_date"].isoformat()] = r["count"]
    return counts
