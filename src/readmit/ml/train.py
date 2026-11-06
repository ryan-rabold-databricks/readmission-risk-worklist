"""Entry point for <env>_readmit_model_training (monthly) and the program backfill.

Trains on discharges whose 30-day label had matured by ``as_of``, evaluates on the
most recent two months of those, registers the model as @challenger, and moves
@champion only if the promotion gates pass (readmit.ml.gates).

Point-in-time correct without snapshots: every feature uses only information known
the morning after discharge, and a label that matured by ``as_of`` cannot change later.
Idempotent: a model version already trained for the same ``as_of`` is reused.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import mlflow
import mlflow.artifacts
import mlflow.sklearn
import pandas as pd
from mlflow.exceptions import MlflowException
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from readmit.common.env_guardrail import assert_environment
from readmit.common.spark import get_spark
from readmit.ml import model as model_lib
from readmit.ml.features import DEFAULT_TRAIN_START, FEATURE_COLUMNS, LABEL
from readmit.ml.gates import Gates, decide
from readmit.ml.metrics import EvalMetrics, decile_table, evaluate

CHAMPION = "champion"
CHALLENGER = "challenger"
TEST_WINDOW_DAYS = 60
VALIDATION_FRACTION = 0.2


@dataclass
class TrainResult:
    model_name: str
    version: str
    as_of: str
    promoted: bool
    reused: bool
    champion_version: str | None
    summary: dict


def model_name(catalog: str) -> str:
    return f"{catalog}.readmission_worklist_gold.readmission_risk"


def champion_version(client: MlflowClient, name: str) -> str | None:
    try:
        return client.get_model_version_by_alias(name, CHAMPION).version
    except MlflowException:
        return None


def data_fingerprint(df: pd.DataFrame) -> str:
    """SHA-256 of every training row (features and label), in a stable order. A version
    is reused only when it was trained on exactly this data, so a re-landed source (for
    example a new simulator generator) retrains instead of silently reusing."""
    cols = ["encounter_id", "discharge_date", *FEATURE_COLUMNS, LABEL]
    payload = df[cols].sort_values(["discharge_date", "encounter_id"]).to_csv(index=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _existing_version_for(client: MlflowClient, name: str, as_of: date, fingerprint: str) -> str | None:
    try:
        versions = client.search_model_versions(f"name = '{name}'")
    except MlflowException:
        return None
    # Unity Catalog search results omit tags; read each version's tags directly. Only
    # versions whose training finished (training_complete, written last) are reused.
    matches = []
    for v in versions:
        tags = client.get_model_version(name, v.version).tags or {}
        if (tags.get("as_of_date") == as_of.isoformat() and tags.get("training_complete") == "true"
                and tags.get("training_data_sha256") == fingerprint):
            matches.append(v.version)
    return max(matches, key=int) if matches else None


def training_frame(spark: SparkSession, catalog: str, as_of: date, train_start: date) -> pd.DataFrame:
    df = (
        spark.table(f"{catalog}.readmission_worklist_gold.discharge_features")
        .filter(F.col("discharge_date") >= F.lit(train_start))
        .filter(F.col("label_matured_at") <= F.lit(as_of).cast("timestamp"))
        .select("encounter_id", "discharge_date", *FEATURE_COLUMNS, LABEL)
    )
    return df.toPandas().sort_values(["discharge_date", "encounter_id"]).reset_index(drop=True)


def time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """train / validation (early stopping) / test, strictly ordered in time."""
    test_start = df["discharge_date"].max() - timedelta(days=TEST_WINDOW_DAYS)
    fit_part, test = df[df["discharge_date"] < test_start], df[df["discharge_date"] >= test_start]
    cut = fit_part["discharge_date"].quantile(1 - VALIDATION_FRACTION, interpolation="nearest")
    return fit_part[fit_part["discharge_date"] < cut], fit_part[fit_part["discharge_date"] >= cut], test


def _log_calibration(deciles: list[dict], directory: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    table = pd.DataFrame(deciles)
    csv = directory / "calibration_by_decile.csv"
    table.to_csv(csv, index=False)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(table["mean_predicted"], table["observed_rate"], marker="o", label="Model")
    top = max(table["mean_predicted"].max(), table["observed_rate"].max()) * 1.05
    ax.plot([0, top], [0, top], linestyle="--", color="grey", label="Perfect calibration")
    ax.set_xlabel("Predicted readmission rate (decile mean)")
    ax.set_ylabel("Actual readmission rate")
    ax.set_title("Predicted vs. actual 30-day readmission by risk decile")
    ax.legend()
    png = directory / "calibration_by_decile.png"
    fig.savefig(png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return [csv, png]


def train_and_maybe_promote(
    spark: SparkSession,
    catalog: str,
    experiment_id: str,
    as_of: date,
    train_start: date,
    gates: Gates,
    force: bool = False,
) -> TrainResult:
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment(experiment_id=experiment_id)
    client = MlflowClient(registry_uri="databricks-uc")
    name = model_name(catalog)

    data = training_frame(spark, catalog, as_of, train_start)
    if data.empty:
        raise RuntimeError(f"No matured training labels between {train_start} and {as_of}")
    fingerprint = data_fingerprint(data)
    existing = None if force else _existing_version_for(client, name, as_of, fingerprint)
    if existing:
        mv = client.get_model_version(name, existing)
        summary = mlflow.artifacts.load_dict(f"runs:/{mv.run_id}/training_summary.json")
        return TrainResult(name, existing, as_of.isoformat(), mv.tags.get("promoted") == "true", True,
                           champion_version(client, name), summary)
    train, val, test = time_split(data)
    X = {k: model_lib.model_frame(v) for k, v in (("train", train), ("val", val), ("test", test))}
    y = {k: v[LABEL].astype(int).values for k, v in (("train", train), ("val", val), ("test", test))}

    pipeline = model_lib.fit(X["train"], y["train"], X["val"], y["val"])
    p_test = model_lib.predict_proba(pipeline, X["test"])
    challenger = evaluate(y["test"], p_test)

    current = champion_version(client, name)
    champion: EvalMetrics | None = None
    if current:
        champ_model = mlflow.sklearn.load_model(f"models:/{name}/{current}")
        champion = evaluate(y["test"], model_lib.predict_proba(champ_model, X["test"]))
    decision = decide(challenger, champion, gates)

    windows = {
        "train": f"{train.discharge_date.min()}..{train.discharge_date.max()}",
        "validation": f"{val.discharge_date.min()}..{val.discharge_date.max()}",
        "test": f"{test.discharge_date.min()}..{test.discharge_date.max()}",
    }
    summary = {
        "as_of": as_of.isoformat(),
        "training_data_sha256": fingerprint,
        "rows": {"train": len(train), "validation": len(val), "test": len(test)},
        "windows": windows,
        "best_iteration": int(pipeline.named_steps["clf"].best_iteration),
        "challenger_test": challenger.as_dict(),
        "champion_version": current,
        "champion_test": champion.as_dict() if champion else None,
        "promoted": decision.promote,
        "gate_reasons": decision.reasons,
    }

    with mlflow.start_run(run_name=f"readmission_risk_as_of_{as_of.isoformat()}"):
        mlflow.log_params({**{k: v for k, v in model_lib.XGB_PARAMS.items()}, "as_of": as_of.isoformat(),
                           "train_start": train_start.isoformat(), **{f"window_{k}": v for k, v in windows.items()}})
        mlflow.log_metrics(challenger.as_dict("test_"))
        if champion:
            mlflow.log_metrics(champion.as_dict("champion_test_"))
        mlflow.log_metric("promoted", int(decision.promote))
        deciles = decile_table(y["test"], p_test)
        summary["calibration_by_decile"] = deciles
        with tempfile.TemporaryDirectory() as tmp:
            for path in _log_calibration(deciles, Path(tmp)):
                mlflow.log_artifact(str(path))
        mlflow.log_dict(summary, "training_summary.json")
        info = mlflow.sklearn.log_model(
            sk_model=pipeline,
            name="model",
            registered_model_name=name,
            signature=infer_signature(X["test"], p_test),
            input_example=X["test"].head(5),
        )

    version = str(info.registered_model_version)
    # Tag values are limited to 1,000 characters; the full summary is the run artifact.
    for key, value in {
        "as_of_date": as_of.isoformat(),
        "training_data_sha256": fingerprint,
        "promoted": str(decision.promote).lower(),
        "test_auc": f"{challenger.auc:.4f}",
        "test_brier": f"{challenger.brier:.5f}",
        "test_calibration_slope": f"{challenger.calibration_slope:.3f}",
    }.items():
        client.set_model_version_tag(name, version, key, value)
    client.set_registered_model_alias(name, CHALLENGER, version)
    if decision.promote:
        client.set_registered_model_alias(name, CHAMPION, version)
    # Written last: marks the version as safe to reuse on rerun.
    client.set_model_version_tag(name, version, "training_complete", "true")
    return TrainResult(name, version, as_of.isoformat(), decision.promote, False,
                       champion_version(client, name), summary)


def format_result(r: TrainResult) -> str:
    s = r.summary
    lines = [
        f"model {r.model_name} v{r.version} as_of={r.as_of} "
        f"{'(reused existing version)' if r.reused else ''}".rstrip(),
        f"promoted={r.promoted} champion=v{r.champion_version}",
    ]
    if s:
        c = s["challenger_test"]
        lines += [
            f"rows: {s['rows']}  windows: {s['windows']}",
            f"test AUC={c['auc']:.4f} Brier={c['brier']:.5f} calibration slope={c['calibration_slope']:.3f} "
            f"intercept={c['calibration_intercept']:.3f} observed={c['observed_rate']:.3%} "
            f"mean_predicted={c['mean_predicted']:.3%}",
        ]
        if s.get("champion_test"):
            ch = s["champion_test"]
            lines.append(f"champion v{s['champion_version']} on same test: AUC={ch['auc']:.4f} Brier={ch['brier']:.5f}")
        lines += [f"gate: {reason}" for reason in s["gate_reasons"]]
        if "calibration_by_decile" in s:
            lines.append("decile | n | mean_predicted | observed_rate")
            lines += [f"{d['decile']:>6} | {d['n']:>5} | {d['mean_predicted']:.3f} | {d['observed_rate']:.3f}"
                      for d in s["calibration_by_decile"]]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--as-of", default="", help="YYYY-MM-DD; empty means today (UTC)")
    p.add_argument("--train-start", default=DEFAULT_TRAIN_START, type=date.fromisoformat)
    p.add_argument("--min-auc", type=float, default=Gates.min_auc)
    p.add_argument("--slope-min", type=float, default=Gates.slope_min)
    p.add_argument("--slope-max", type=float, default=Gates.slope_max)
    p.add_argument("--auc-tolerance", type=float, default=Gates.auc_tolerance)
    p.add_argument("--force", action="store_true", help="Retrain even if this as_of was already trained")
    return p.parse_args(argv)


def gates_from(args: argparse.Namespace) -> Gates:
    return Gates(args.min_auc, args.slope_min, args.slope_max, args.auc_tolerance)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog)
    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc).date()
    result = train_and_maybe_promote(
        get_spark(), args.catalog, args.experiment_id, as_of, args.train_start, gates_from(args), args.force
    )
    print(format_result(result))


if __name__ == "__main__":
    main()
