"""Entry point for <env>_readmit_source_simulator.

Lands every missing daily EHR extract from history_start through run_date (default:
yesterday, UTC) into the ehr_landing volume. The first run backfills the full
history; later runs land only the new days. Already-landed dates are never rewritten,
so the job is safe to rerun.
"""

from __future__ import annotations

import argparse
import uuid
from datetime import date, datetime, timedelta, timezone

from pyspark.sql import functions as F

from readmit.common.env_guardrail import assert_environment
from readmit.common.spark import get_spark
from readmit.simulator.config import SimulatorConfig
from readmit.simulator.generate import ENTITIES, build_universe
from readmit.simulator.summary import extract_counts, story_report

# Bump when the extract schema or generation logic changes; see assert_single_generator_version.
GENERATOR_VERSION = "2"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--history-start", required=True, type=date.fromisoformat)
    p.add_argument("--run-date", default="", help="YYYY-MM-DD; empty means yesterday (UTC)")
    p.add_argument("--avg-readmission-cost", type=float, default=15000.0)
    p.add_argument("--dry-run", action="store_true", help="Build and report; land nothing")
    return p.parse_args(argv)


def resolve_run_date(raw: str, today: date) -> date:
    run_date = date.fromisoformat(raw) if raw else today - timedelta(days=1)
    if run_date >= today:
        raise ValueError(f"run_date {run_date} must be before today ({today}); extracts are for completed days")
    return run_date


def missing_dates(history_start: date, run_date: date, landed: set[date]) -> list[date]:
    span = (run_date - history_start).days + 1
    return [d for d in (history_start + timedelta(days=i) for i in range(span)) if d not in landed]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog)
    today = datetime.now(timezone.utc).date()
    cfg = SimulatorConfig(history_start=args.history_start, run_date=resolve_run_date(args.run_date, today))
    volume_root = f"/Volumes/{args.catalog}/ehr_raw/ehr_landing"
    print(f"env={args.env} catalog={args.catalog} history_start={cfg.history_start} run_date={cfg.run_date}")

    spark = get_spark()
    universe = build_universe(spark, cfg)

    if args.dry_run:
        print("Dry run: nothing landed.")
        print(story_report(universe.inpatient, cfg.run_date, args.avg_readmission_cost))
        return

    from databricks.sdk import WorkspaceClient

    from readmit.simulator.landing import VolumeLanding, assert_single_generator_version, landed_dates

    landing = VolumeLanding(WorkspaceClient(), volume_root)
    manifests = landing.manifests()
    assert_single_generator_version(manifests, GENERATOR_VERSION)
    landed = landed_dates(manifests)
    targets = missing_dates(cfg.history_start, cfg.run_date, landed)
    if not targets:
        print(f"All extract dates through {cfg.run_date} are already landed; nothing to do.")
        return

    removed = landing.remove_unmanifested(ENTITIES, landed)
    if removed:
        print(f"Removed {len(removed)} partial date folders from an interrupted run.")

    target_strs = [d.isoformat() for d in targets]
    to_land = {
        entity: df.filter(F.col("extract_date").cast("string").isin(target_strs))
        for entity, df in universe.extracts.items()
    }
    for entity, df in to_land.items():
        (
            df.repartition("extract_date")
            .write.mode("append")
            .partitionBy("extract_date")
            .option("timestampFormat", "yyyy-MM-dd'T'HH:mm:ss")
            .json(f"{volume_root}/{entity}")
        )
        print(f"Landed {entity}")

    counts = extract_counts(to_land)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    manifest = landing.write_manifest(
        run_id,
        targets,
        counts,
        {"generator_version": GENERATOR_VERSION, "seed": cfg.seed, "history_start": cfg.history_start.isoformat()},
    )
    print(f"Landed {len(targets)} extract dates ({targets[0]} to {targets[-1]}); manifest {manifest}")
    for entity in ENTITIES:
        print(f"  {entity}: {sum(counts[entity].values()):,} records")
    print(story_report(universe.inpatient, cfg.run_date, args.avg_readmission_cost))


if __name__ == "__main__":
    main()
