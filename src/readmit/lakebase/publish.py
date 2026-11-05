"""publish_worklist task: push the day's gold worklist and roster to Lakebase.

Synced tables are TRIGGERED, so each sync runs once per daily cycle, after
build_worklist has written the whole day. Each sync is an incremental update of its
managed pipeline (change data feed on the source). The task then checks that
Postgres holds exactly the rows UC holds for the published day.
"""

from __future__ import annotations

import argparse
import json
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.pipelines import UpdateInfoState

from readmit.common.dates import parse_or_today
from readmit.common.env_guardrail import assert_environment
from readmit.common.spark import get_spark
from readmit.lakebase.app_schema import SYNCED_SCHEMA
from readmit.lakebase.connect import LakebaseTarget, connect

# Synced table -> (source table, date column used for the row-count check).
SYNCED_TABLES = {
    "care_worklist_synced": ("care_worklist", "worklist_date"),
    "care_team_roster_synced": ("care_team_roster", "roster_date"),
}
FINAL = {UpdateInfoState.COMPLETED, UpdateInfoState.FAILED, UpdateInfoState.CANCELED}
SYNC_TIMEOUT_S = 1800


def pipeline_id(w: WorkspaceClient, catalog: str, synced: str) -> str:
    st = w.postgres.get_synced_table(name=f"synced_tables/{catalog}.{SYNCED_SCHEMA}.{synced}")
    if not st.status or not st.status.pipeline_id:
        raise RuntimeError(f"Synced table {synced} has no pipeline yet: {st.status}")
    return st.status.pipeline_id


def run_sync(w: WorkspaceClient, pid: str) -> dict:
    # The managed pipeline may still be finishing an earlier update; wait for it.
    deadline = time.time() + SYNC_TIMEOUT_S
    while (p := w.pipelines.get(pid)).latest_updates and p.latest_updates[0].state not in FINAL:
        if time.time() > deadline:
            raise TimeoutError(f"Pipeline {pid} busy for {SYNC_TIMEOUT_S}s")
        time.sleep(15)
    update_id = w.pipelines.start_update(pid).update_id
    while True:
        u = w.pipelines.get_update(pid, update_id).update
        if u.state in FINAL:
            break
        if time.time() > deadline:
            raise TimeoutError(f"Sync update {update_id} on {pid} did not finish in {SYNC_TIMEOUT_S}s")
        time.sleep(15)
    if u.state != UpdateInfoState.COMPLETED:
        raise RuntimeError(f"Sync update {update_id} on pipeline {pid} ended {u.state}")
    return {"pipeline_id": pid, "update_id": update_id, "state": u.state.value}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--run-date", default="", help="Worklist day to verify; empty means today (UTC)")
    p.add_argument("--lakebase-project", required=True)
    p.add_argument("--lakebase-branch", required=True)
    p.add_argument("--lakebase-database", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog, args.lakebase_project, args.lakebase_database)
    w = WorkspaceClient()
    spark = get_spark()
    run_date = parse_or_today(args.run_date)
    target = LakebaseTarget(args.lakebase_project, args.lakebase_branch, args.lakebase_database)
    summary = {"run_date": run_date.isoformat(), "tables": {}}
    for synced, (source, date_col) in SYNCED_TABLES.items():
        result = run_sync(w, pipeline_id(w, args.catalog, synced))
        uc_rows = spark.table(f"{args.catalog}.{SYNCED_SCHEMA}.{source}").filter(f"{date_col} = DATE'{run_date}'").count()
        with connect(w, target) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {SYNCED_SCHEMA}.{synced} WHERE {date_col} = %s", (run_date,))
            pg_rows = cur.fetchone()[0]
        result.update(uc_rows=uc_rows, pg_rows=pg_rows)
        summary["tables"][synced] = result
        if uc_rows != pg_rows:
            raise RuntimeError(f"{synced}: Postgres has {pg_rows} rows for {run_date}, UC has {uc_rows}: {summary}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
