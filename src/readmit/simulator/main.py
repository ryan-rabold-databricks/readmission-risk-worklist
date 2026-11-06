"""Entry point for <env>_readmit_source_simulator.

Lands every missing daily EHR extract from history_start through run_date (default:
yesterday, UTC) into the ehr_landing volume. The first run backfills the full
history; later runs land only the new days. Already-landed dates are never rewritten,
so the job is safe to rerun.

Program response (generator v4): the simulated world reacts to outreach the app has
captured. Reached patients are read from the Lakebase CDF landing table
readmission_worklist_app_bronze.lb_outreach_activity_history (current state), so a
reach can only change events that land after it (DECISIONS.md #45).
"""

from __future__ import annotations

import argparse
import uuid
from datetime import date, datetime, timedelta, timezone

from pyspark.sql import functions as F

from readmit.common.env_guardrail import assert_environment
from readmit.common.spark import get_spark
from readmit.simulator.config import SimulatorConfig
from readmit.pipeline.source_schemas import SOURCE_SCHEMAS
from readmit.simulator.generate import ENTITIES, LOOKAHEAD_DAYS, build_universe
from readmit.simulator.summary import extract_counts, story_report

# Bump when the extract schema or generation logic changes; see assert_single_generator_version.
GENERATOR_VERSION = "4"
OUTREACH_HISTORY = "readmission_worklist_app_bronze.lb_outreach_activity_history"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--history-start", required=True, type=date.fromisoformat)
    p.add_argument("--run-date", default="", help="YYYY-MM-DD; empty means yesterday (UTC)")
    p.add_argument("--avg-readmission-cost", type=float, default=15000.0)
    p.add_argument("--dry-run", action="store_true", help="Build and report; land nothing")
    p.add_argument("--no-program-response", action="store_true",
                   help="Ignore captured outreach (output matches generator v3)")
    return p.parse_args(argv)


def resolve_run_date(raw: str, today: date) -> date:
    run_date = date.fromisoformat(raw) if raw else today - timedelta(days=1)
    if run_date >= today:
        raise ValueError(f"run_date {run_date} must be before today ({today}); extracts are for completed days")
    return run_date


def missing_dates(history_start: date, run_date: date, landed: set[date]) -> list[date]:
    span = (run_date - history_start).days + 1
    return [d for d in (history_start + timedelta(days=i) for i in range(span)) if d not in landed]


def load_reach(spark, catalog: str):
    """First REACHED call per worklist item, from the current state of the CDF history
    (latest change per activity_id; deleted activities drop out). None if no history."""
    table = f"{catalog}.{OUTREACH_HISTORY}"
    if not spark.catalog.tableExists(table):
        return None
    return spark.sql(f"""
        SELECT worklist_item_id, min(activity_ts) AS reach_ts
        FROM (
          SELECT *, row_number() OVER (PARTITION BY activity_id ORDER BY _pg_lsn DESC, _sort_by DESC) AS rn
          FROM {table}
          WHERE _pg_change_type IN ('insert', 'update_postimage', 'delete')
        )
        WHERE rn = 1 AND _pg_change_type != 'delete' AND activity_type = 'REACHED'
        GROUP BY worklist_item_id""").localCheckpoint()


def program_summary(universe, run_date: date) -> str:
    row = (universe.inpatient.filter(F.col("is_index") & (F.to_date("discharge_ts") <= F.lit(run_date)))
           .agg(F.sum(F.col("reach_ts").isNotNull().cast("int")).alias("reached"),
                F.sum(F.col("cm_followup_booked").cast("int")).alias("cm_bookings"),
                F.sum(F.col("readmit_prevented").cast("int")).alias("prevented"))
           .first())
    return (f"Program response: reached index stays={row.reached or 0}, care-manager follow-ups booked="
            f"{row.cm_bookings or 0}, readmissions prevented={row.prevented or 0}")


def late_records(spark, universe_df, entity: str, volume_root: str, dates: list[date]):
    """Records the generator places on already-landed dates that the landing zone lacks.

    Multiset difference (exceptAll), so re-sent duplicates are compared correctly.
    """
    if not dates:
        return None
    strs = [d.isoformat() for d in dates]
    landed = (
        spark.read.schema(SOURCE_SCHEMAS[entity]).option("timestampFormat", "yyyy-MM-dd'T'HH:mm:ss")
        .json(f"{volume_root}/{entity}")
        .filter(F.col("extract_date").cast("string").isin(strs))
    )
    expected = universe_df.filter(F.col("extract_date").cast("string").isin(strs))
    cols = landed.columns
    return expected.select(*cols).exceptAll(landed.select(*cols))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog)
    today = datetime.now(timezone.utc).date()
    cfg = SimulatorConfig(history_start=args.history_start, run_date=resolve_run_date(args.run_date, today))
    volume_root = f"/Volumes/{args.catalog}/ehr_raw/ehr_landing"
    print(f"env={args.env} catalog={args.catalog} history_start={cfg.history_start} run_date={cfg.run_date}")

    spark = get_spark()
    reach = None if args.no_program_response else load_reach(spark, args.catalog)
    print(f"Program response input: {reach.count() if reach is not None else 0} reached worklist items")
    universe = build_universe(spark, cfg, reach)

    if args.dry_run:
        print("Dry run: nothing landed.")
        print(story_report(universe.inpatient, cfg.run_date, args.avg_readmission_cost))
        print(program_summary(universe, cfg.run_date))
        return

    from databricks.sdk import WorkspaceClient

    from readmit.simulator.landing import VolumeLanding, assert_single_generator_version, landed_dates

    landing = VolumeLanding(WorkspaceClient(), volume_root)
    manifests = landing.manifests()
    assert_single_generator_version(manifests, GENERATOR_VERSION)
    landed = landed_dates(manifests)
    targets = missing_dates(cfg.history_start, cfg.run_date, landed)
    recent_landed = sorted(d for d in landed if d > cfg.run_date - timedelta(days=LOOKAHEAD_DAYS))
    late = {e: late_records(spark, universe.extracts[e], e, volume_root, recent_landed) for e in ENTITIES}
    late_counts = {e: (df.count() if df is not None else 0) for e, df in late.items()}
    if not targets and not any(late_counts.values()):
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
    for entity, extra in late.items():
        if late_counts[entity]:
            # Late-arriving records for dates already landed: appended to their date folder.
            to_land[entity] = to_land[entity].unionByName(extra)
    if any(late_counts.values()):
        print(f"Late-arriving records for already-landed dates: {late_counts}")
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
        {"generator_version": GENERATOR_VERSION, "seed": cfg.seed, "history_start": cfg.history_start.isoformat(),
         "late_records": late_counts},
    )
    span = f" ({targets[0]} to {targets[-1]})" if targets else ""
    print(f"Landed {len(targets)} new extract dates{span}; manifest {manifest}")
    for entity in ENTITIES:
        print(f"  {entity}: {sum(counts[entity].values()):,} records")
    print(story_report(universe.inpatient, cfg.run_date, args.avg_readmission_cost))
    print(program_summary(universe, cfg.run_date))


if __name__ == "__main__":
    main()
