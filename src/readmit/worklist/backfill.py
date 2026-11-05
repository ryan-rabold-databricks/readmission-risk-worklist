"""Entry point for <env>_readmit_program_backfill (demo only, DECISIONS.md #29).

Replays the program from go_live through run_date, one month at a time:
1. Monthly retrain as of the 1st (train_and_maybe_promote), as the training job would.
2. Score and build every worklist day of that month with the then-current @champion.
Then drafts outreach briefs for the last ``brief_days`` worklist days only.
Every step is idempotent, so the backfill can be rerun or resumed safely.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from readmit.common.dates import date_range, month_starts, parse_or_today
from readmit.common.env_guardrail import assert_environment
from readmit.common.spark import get_spark
from readmit.ml.features import DEFAULT_TRAIN_START
from readmit.ml.gates import Gates
from readmit.ml.score import score_worklist_date
from readmit.ml.train import format_result, train_and_maybe_promote
from readmit.worklist.build import build_worklist_date, generate_briefs
from readmit.worklist.tables import ensure_tables


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--go-live", required=True, type=date.fromisoformat)
    p.add_argument("--run-date", default="", help="Last worklist day; empty means today (UTC)")
    p.add_argument("--train-start", default=DEFAULT_TRAIN_START, type=date.fromisoformat)
    p.add_argument("--llm-endpoint", required=True)
    p.add_argument("--brief-days", type=int, default=14)
    p.add_argument("--process", required=True)
    p.add_argument("--min-auc", type=float, default=Gates.min_auc)
    p.add_argument("--slope-min", type=float, default=Gates.slope_min)
    p.add_argument("--slope-max", type=float, default=Gates.slope_max)
    p.add_argument("--auc-tolerance", type=float, default=Gates.auc_tolerance)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog)
    spark = get_spark()
    ensure_tables(spark, args.catalog)
    run_date = parse_or_today(args.run_date)
    gates = Gates(args.min_auc, args.slope_min, args.slope_max, args.auc_tolerance)

    starts = month_starts(args.go_live, run_date)
    # The then-current champion is tracked here, not read from the @champion alias:
    # on a rerun the alias already points at the latest month's model, and scoring
    # history with it would add duplicate scores under new run ids.
    version: str | None = None
    for i, start in enumerate(starts):
        print(f"== Month starting {start}: monthly retrain as of {start}")
        result = train_and_maybe_promote(spark, args.catalog, args.experiment_id, start, args.train_start, gates)
        print(format_result(result))
        if result.promoted:
            version = result.version
        if version is None:
            raise RuntimeError(f"No model passed the first-model gates as of {start}; cannot score")
        print(f"then-current champion for {start}: v{version}")
        end = min(run_date, (starts[i + 1] - timedelta(days=1)) if i + 1 < len(starts) else run_date)
        for d in date_range(start, end):
            scored = score_worklist_date(spark, args.catalog, version, d, args.process)
            built = build_worklist_date(spark, args.catalog, d, args.process)
            print(f"{d}: scored={scored} v{version} worklist={built}")

    since = run_date - timedelta(days=args.brief_days - 1)
    print(generate_briefs(spark, args.catalog, args.llm_endpoint, since, args.process))


if __name__ == "__main__":
    main()
