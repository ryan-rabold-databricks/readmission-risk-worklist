"""build_worklist task: roster, capacity-capped routing, and outreach briefs.

For each worklist day W (catching up from the last built day):
1. care_team_roster for W: active facility assignments joined to each care manager's
   active daily capacity.
2. care_worklist for W: scored discharges whose tier is included in the worklist,
   routed highest risk first within each care manager's capacity; the rest are
   OVERFLOW (visible, unassigned). Existing items are never re-routed on rerun.
3. Outreach briefs (ai_query) for items on the most recent ``brief_days`` worklist
   days that do not have one yet. The prompt carries the minimum necessary: no name,
   MRN, or phone (DECISIONS.md #31).
"""

from __future__ import annotations

import argparse
import re
from datetime import date, timedelta

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from readmit.common.dates import date_range, parse_or_today, release_ts
from readmit.common.env_guardrail import assert_environment
from readmit.common.spark import get_spark
from readmit.ml.drivers import CONDITION_LABELS, DISPOSITION_LABELS
from readmit.pipeline.audit import refresh_audit_columns
from readmit.pipeline.keys import hash_key
from readmit.worklist.assign import assign_items
from readmit.worklist.tables import ensure_tables, table

_ENDPOINT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
# Fail the task when more than this share of brief calls error (after saving successes).
MAX_BRIEF_ERROR_RATE = 0.10
# The brief budget must cover the model's hidden reasoning as well as the visible text:
# at 300 tokens databricks-claude-opus-5-5 returned empty strings with no error.
BRIEF_MAX_TOKENS = 2000
# A brief shorter than this is treated as failed and regenerated on the next run.
MIN_BRIEF_CHARS = 80


def _active_on(df: DataFrame, d: date) -> DataFrame:
    return df.filter((F.col("effective_date") <= F.lit(d)) & (F.col("expiration_date").isNull() | (F.col("expiration_date") > F.lit(d))))


def build_roster(spark: SparkSession, catalog: str, d: date, process: str) -> pd.DataFrame:
    cm = f"{catalog}.care_management_silver"
    roster = (
        _active_on(spark.table(f"{cm}.care_team_assignment"), d)
        .select("care_manager_email", "facility_id")
        .join(_active_on(spark.table(f"{cm}.care_manager_capacity"), d).select("care_manager_email", "daily_capacity"),
              "care_manager_email")
        .select(
            hash_key("care_manager_email", "facility_id", F.lit(d)).alias("roster_id"),
            "care_manager_email", "facility_id", F.lit(d).alias("roster_date"), "daily_capacity",
            *refresh_audit_columns(process, F.lit(f"worklist:{d.isoformat()}")),
        )
    )
    roster.createOrReplaceTempView("_roster")
    spark.sql(
        f"MERGE INTO {table(catalog, 'care_team_roster')} t USING _roster s ON t.roster_id = s.roster_id "
        "WHEN NOT MATCHED THEN INSERT *"
    )
    return spark.table(table(catalog, "care_team_roster")).filter(F.col("roster_date") == F.lit(d)).toPandas()


def build_worklist_date(spark: SparkSession, catalog: str, d: date, process: str) -> dict:
    target = table(catalog, "care_worklist")
    if spark.table(target).filter(F.col("worklist_date") == F.lit(d)).limit(1).count():
        return {"worklist_date": d.isoformat(), "skipped": "already built"}
    scores = spark.table(table(catalog, "discharge_risk_score")).filter(F.col("worklist_date") == F.lit(d))
    if not scores.limit(1).count():
        return {"worklist_date": d.isoformat(), "skipped": "not scored yet"}

    roster = build_roster(spark, catalog, d, process)
    latest_first = Window.partitionBy("encounter_id").orderBy(F.desc("scored_at"))
    latest = scores.withColumn("_rn", F.row_number().over(latest_first)).filter("_rn = 1").drop("_rn")
    policy = spark.table(f"{catalog}.care_management_silver.risk_tier_policy").filter("is_active")
    features = spark.table(f"{catalog}.readmission_worklist_gold.discharge_features").select(
        "encounter_id", "patient_id", "facility_id"
    )
    patients = spark.table(f"{catalog}.clinical_silver.patient").select(
        "patient_id", F.concat_ws(" ", "first_name", "last_name").alias("patient_display_name"), "phone"
    )
    candidates = (
        latest.join(policy.filter("include_in_worklist").select("risk_tier", "outreach_sla_hours"), "risk_tier")
        .join(features, "encounter_id")
        .join(patients, "patient_id")
        .withColumn("worklist_item_id", hash_key("encounter_id"))
    )
    items = candidates.select("worklist_item_id", "facility_id", "risk_score").toPandas()
    assignments = pd.DataFrame(
        [a.__dict__ for a in assign_items(items.to_dict("records"), roster.to_dict("records"))],
        columns=["worklist_item_id", "care_manager_email", "status"],
    )
    released = release_ts(d)
    routed = spark.createDataFrame(assignments, "worklist_item_id STRING, care_manager_email STRING, status STRING")
    rows = candidates.join(routed, "worklist_item_id").select(
        "worklist_item_id", "encounter_id", "score_id", "patient_id", "facility_id",
        F.lit(d).alias("worklist_date"),
        F.col("status").alias("assignment_status"),
        F.col("care_manager_email").alias("assigned_care_manager"),
        "patient_display_name", "phone", "risk_score", "risk_tier", "top_drivers",
        F.lit(None).cast("string").alias("outreach_brief"),
        (F.lit(released).cast("timestamp") + F.make_interval(hours=F.col("outreach_sla_hours"))).alias("due_at"),
        F.lit(released).cast("timestamp").alias("created_at"),
        *refresh_audit_columns(process, F.lit(f"worklist:{d.isoformat()}")),
    )
    rows.createOrReplaceTempView("_new_items")
    spark.sql(
        f"MERGE INTO {target} t USING _new_items s ON t.worklist_item_id = s.worklist_item_id "
        "WHEN NOT MATCHED THEN INSERT *"
    )
    counts = assignments["status"].value_counts().to_dict()
    return {"worklist_date": d.isoformat(), "items": len(assignments), **counts,
            "roster_capacity": int(roster.drop_duplicates("care_manager_email")["daily_capacity"].sum()) if len(roster) else 0}


def _prompt() -> F.Column:
    cond = F.coalesce(
        F.element_at(F.create_map(*[x for k, v in CONDITION_LABELS.items() for x in (F.lit(k), F.lit(v))]),
                     F.col("primary_condition_group")),
        F.lit("Admission diagnosis"),
    )
    disp = F.coalesce(
        F.element_at(F.create_map(*[x for k, v in DISPOSITION_LABELS.items() for x in (F.lit(k), F.lit(v))]),
                     F.col("discharge_disposition")),
        F.lit("Discharge disposition not recorded"),
    )
    return F.concat(
        F.lit(
            "You are drafting a call brief for a hospital care manager who will phone a recently "
            "discharged patient to help prevent a readmission within 30 days. Write exactly three short "
            "bullet points, 70 words or fewer in total: (1) why this patient is at risk, using only the "
            "facts below; (2) what to ask or check on the call; (3) the recommended next step. Use only "
            "the facts given; do not invent diagnoses, medications, or history, and do not refer to the "
            "patient by name.\nFacts:\n- Risk tier: "
        ),
        F.col("risk_tier"), F.lit(" (predicted 30-day readmission risk "),
        F.format_number(F.col("risk_score") * 100, 0), F.lit("%)\n- Primary condition: "), cond,
        F.lit("\n- Top risk drivers: "), F.concat_ws("; ", "top_drivers"),
        F.lit("\n- Discharge: "), disp,
        F.lit("\n- Follow-up within 7 days booked: "),
        F.when(F.col("followup_scheduled_7d"), "yes").otherwise("no"),
        F.lit("\n- Call due by: "), F.date_format("due_at", "yyyy-MM-dd HH:mm 'UTC'"),
    )


def _missing_brief(col: F.Column) -> F.Column:
    return col.isNull() | (F.length(F.trim(col)) < MIN_BRIEF_CHARS)


def generate_briefs(spark: SparkSession, catalog: str, endpoint: str, since: date, process: str) -> dict:
    if not _ENDPOINT_NAME.match(endpoint):
        raise ValueError(f"Invalid serving endpoint name: {endpoint!r}")
    target = table(catalog, "care_worklist")
    todo = (
        spark.table(target)
        .filter(_missing_brief(F.col("outreach_brief")) & (F.col("worklist_date") >= F.lit(since)))
        .join(spark.table(f"{catalog}.readmission_worklist_gold.discharge_features")
              .select("encounter_id", "primary_condition_group", "discharge_disposition", "followup_scheduled_7d"),
              "encounter_id")
    )
    pending = todo.count()
    if not pending:
        return {"briefs_requested": 0}
    answered = (
        todo.select("worklist_item_id", _prompt().alias("prompt"))
        .withColumn(
            "ai",
            F.expr(
                # Only max_tokens: some chat endpoints (e.g. databricks-claude-opus-5-5) reject temperature.
                f"ai_query('{endpoint}', prompt, failOnError => false, "
                f"modelParameters => named_struct('max_tokens', {BRIEF_MAX_TOKENS}))"
            ),
        )
    )
    # With failOnError => false, ai_query returns STRUCT<result, errorMessage> on current
    # runtimes (some references document `response`); read whichever is present.
    fields = {f.name for f in answered.schema["ai"].dataType.fields}
    text_field = "result" if "result" in fields else "response"
    answered = answered.select(
        "worklist_item_id", F.col(f"ai.{text_field}").alias("brief"), F.col("ai.errorMessage").alias("error")
    )
    # Materialize once: each row is one billed LLM call.
    results = answered.toPandas()
    usable = results["brief"].fillna("").str.strip().str.len() >= MIN_BRIEF_CHARS
    results.loc[~usable & results["error"].fillna("").eq(""), "error"] = "empty or truncated response"
    ok = results[usable]
    if len(ok):
        spark.createDataFrame(ok[["worklist_item_id", "brief"]]).createOrReplaceTempView("_briefs")
        spark.sql(
            f"MERGE INTO {target} t USING _briefs s ON t.worklist_item_id = s.worklist_item_id "
            f"WHEN MATCHED AND (t.outreach_brief IS NULL OR length(trim(t.outreach_brief)) < {MIN_BRIEF_CHARS}) "
            "THEN UPDATE SET t.outreach_brief = s.brief, "
            f"t.audit_updated_at = current_timestamp(), t.audit_updated_by = current_user(), "
            f"t.audit_updated_process = '{process}', t.audit_updated_run_id = 'briefs:{date.today().isoformat()}'"
        )
    errors = results[~usable]["error"].dropna().head(3).tolist()
    outcome = {"briefs_requested": pending, "briefs_written": len(ok), "brief_errors": len(results) - len(ok),
               "sample_errors": errors}
    if outcome["brief_errors"] > MAX_BRIEF_ERROR_RATE * len(results):
        raise RuntimeError(f"Outreach brief generation failed for too many items: {outcome}")
    return outcome


def pending_worklist_dates(spark: SparkSession, catalog: str, go_live: date, run_date: date) -> list[date]:
    last = spark.table(table(catalog, "care_worklist")).agg(F.max("worklist_date")).first()[0]
    start = max(go_live, last + timedelta(days=1)) if last else max(go_live, run_date)
    return date_range(start, run_date)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--run-date", default="", help="Worklist day to build through; empty means today (UTC)")
    p.add_argument("--go-live", required=True, type=date.fromisoformat)
    p.add_argument("--llm-endpoint", required=True)
    p.add_argument("--brief-days", type=int, default=14)
    p.add_argument("--process", required=True, help="Job name recorded in audit columns")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog)
    spark = get_spark()
    ensure_tables(spark, args.catalog)
    run_date = parse_or_today(args.run_date)
    for d in pending_worklist_dates(spark, args.catalog, args.go_live, run_date):
        print(build_worklist_date(spark, args.catalog, d, args.process))
    since = run_date - timedelta(days=args.brief_days - 1)
    print(generate_briefs(spark, args.catalog, args.llm_endpoint, since, args.process))


if __name__ == "__main__":
    main()
