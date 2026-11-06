"""score_discharges task: score each worklist day's discharges with a model version.

Worklist day W covers discharges on W - 1 (scored the morning after). Scores append to
readmission_worklist_gold.discharge_risk_score keyed by a deterministic scoring_run_id
(<W>:v<version>), so reruns never duplicate. The daily task catches up every worklist
day since the last scored one, using the current @champion.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.tracking import MlflowClient
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from readmit.common.dates import date_range, parse_or_today
from readmit.common.env_guardrail import assert_environment
from readmit.common.spark import get_spark
from readmit.ml import model as model_lib
from readmit.ml.drivers import top_drivers
from readmit.ml.features import FEATURE_COLUMNS
from readmit.ml.tiers import tier_for
from readmit.ml.train import champion_version, model_name
from readmit.pipeline.audit import refresh_audit_columns
from readmit.pipeline.keys import hash_key
from readmit.worklist.tables import ensure_tables, table

_MODELS: dict[str, object] = {}


def _load(name: str, version: str):
    key = f"{name}/{version}"
    if key not in _MODELS:
        _MODELS[key] = mlflow.sklearn.load_model(f"models:/{name}/{version}")
    return _MODELS[key]


def scoring_run_id(worklist_date: date, version: str) -> str:
    return f"{worklist_date.isoformat()}:v{version}"


def score_worklist_date(
    spark: SparkSession, catalog: str, version: str, worklist_date: date, process: str
) -> int:
    """Score discharges on worklist_date - 1 with ``version``; return rows written (0 if already scored)."""
    mlflow.set_registry_uri("databricks-uc")
    name = model_name(catalog)
    run_id = scoring_run_id(worklist_date, version)
    target = table(catalog, "discharge_risk_score")
    if spark.table(target).filter(F.col("scoring_run_id") == run_id).limit(1).count():
        return 0

    features = (
        spark.table(f"{catalog}.readmission_worklist_gold.discharge_features")
        .filter(F.col("discharge_date") == F.lit(worklist_date - timedelta(days=1)))
        .select("encounter_id", *FEATURE_COLUMNS)
        .toPandas()
    )
    if features.empty:
        print(f"{worklist_date}: no discharges on {worklist_date - timedelta(days=1)}; nothing scored")
        return 0

    policy = (
        spark.table(f"{catalog}.care_management_silver.risk_tier_policy")
        .filter("is_active")
        # The policy version in effect on the worklist date (Program Settings changes are effective-dated).
        .filter((F.col("effective_date") <= F.lit(worklist_date))
                & (F.col("expiration_date").isNull() | (F.col("expiration_date") > F.lit(worklist_date))))
        .orderBy("min_score")
        .toPandas()
    )
    pipeline = _load(name, version)
    X = model_lib.model_frame(features)
    scores = model_lib.predict_proba(pipeline, X)
    contrib = model_lib.contributions(pipeline, X)
    rows = [
        {
            "encounter_id": enc,
            "risk_score": float(s),
            "risk_tier": tier_for(float(s), policy),
            "top_drivers": top_drivers(X.iloc[i].to_dict(), contrib.iloc[i].to_dict()),
        }
        for i, (enc, s) in enumerate(zip(features["encounter_id"], scores))
    ]
    batch = spark.createDataFrame(
        pd.DataFrame(rows), "encounter_id STRING, risk_score DOUBLE, risk_tier STRING, top_drivers ARRAY<STRING>"
    ).select(
        hash_key(F.col("encounter_id"), F.lit(version), F.lit(run_id)).alias("score_id"),
        "encounter_id",
        F.lit(name).alias("model_name"),
        F.lit(version).alias("model_version"),
        "risk_score",
        "risk_tier",
        "top_drivers",
        F.lit(worklist_date).alias("worklist_date"),
        F.current_timestamp().alias("scored_at"),
        F.lit(run_id).alias("scoring_run_id"),
        *refresh_audit_columns(process, F.lit(run_id)),
    )
    batch.createOrReplaceTempView("_new_scores")
    spark.sql(
        f"MERGE INTO {target} t USING _new_scores s ON t.score_id = s.score_id WHEN NOT MATCHED THEN INSERT *"
    )
    return len(rows)


def pending_worklist_dates(spark: SparkSession, catalog: str, go_live: date, run_date: date) -> list[date]:
    last = spark.table(table(catalog, "discharge_risk_score")).agg(F.max("worklist_date")).first()[0]
    start = max(go_live, last + timedelta(days=1)) if last else max(go_live, run_date)
    return date_range(start, run_date)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--run-date", default="", help="Worklist day to score through; empty means today (UTC)")
    p.add_argument("--go-live", required=True, type=date.fromisoformat)
    p.add_argument("--process", required=True, help="Job name recorded in audit columns")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog)
    spark = get_spark()
    ensure_tables(spark, args.catalog)
    version = champion_version(MlflowClient(registry_uri="databricks-uc"), model_name(args.catalog))
    if version is None:
        raise RuntimeError("No @champion model; run the model training job (or the program backfill) first")
    dates = pending_worklist_dates(spark, args.catalog, args.go_live, parse_or_today(args.run_date))
    if not dates:
        print("All worklist days are already scored; nothing to do.")
    for d in dates:
        print(f"{d}: scored {score_worklist_date(spark, args.catalog, version, d, args.process)} discharges with v{version}")


if __name__ == "__main__":
    main()
