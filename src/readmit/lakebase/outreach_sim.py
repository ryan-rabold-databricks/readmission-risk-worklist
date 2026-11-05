"""Demo only: simulate care-manager outreach for worklist days before run_date.

Writes through Lakebase, exactly like the app will, so the CDF feed carries the
history into readmission_worklist_app_bronze.lb_outreach_activity_history.

Story (deterministic, hash-based like the EHR simulator, DECISIONS.md #20):
- Only ASSIGNED items are worked; OVERFLOW items get no outreach.
- A small share of assigned items is never attempted.
- Up to three call attempts; each reaches the patient with a tier-specific chance.
  Attempts that miss alternate NO_ANSWER / LEFT_VOICEMAIL with next_step_due_at set
  to the next attempt; a reach is REACHED (or DECLINED); three misses add UNREACHABLE.
- FOLLOWUP_BOOKED is logged only when the EHR shows a follow-up booked after the
  patient was reached, so outreach never contradicts the clinical record.
- Outreach does not change outcomes: the EHR data was generated without it.
- Only activities before the cutoff (release of run_date) are written; reruns with a
  later run_date add the later activities. Inserts are ON CONFLICT DO NOTHING on
  client_request_id, so reruns never duplicate.
- note is always NULL (free text is PHI-prone; IDs only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from readmit.common.dates import parse_or_today, release_ts
from readmit.common.env_guardrail import assert_environment
from readmit.lakebase.app_schema import APP_SCHEMA

SIM_VERSION = "outreach-sim-v1"
ACTIVITY_NAMESPACE = uuid.UUID("6f1d3c2e-8a4b-4f5e-9c7d-2b1a0e9f8d7c")
MAX_ATTEMPTS = 3
REACH_PROBABILITY = {"HIGH": 0.34, "MEDIUM": 0.28}
NOT_ATTEMPTED_RATE = 0.04
DECLINE_RATE = 0.07
INSERT_BATCH = 2000


@dataclass(frozen=True)
class WorkItem:
    worklist_item_id: str
    care_manager_email: str
    risk_tier: str
    created_at: datetime
    due_at: datetime
    followup_booked_ts: datetime | None  # earliest EHR booking after release, if any


def uniform(*parts: object) -> float:
    """Deterministic U[0, 1) from the given parts."""
    h = hashlib.sha256("|".join(map(str, (SIM_VERSION, *parts))).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _activity(item: WorkItem, seq: int, kind: str, ts: datetime, next_due: datetime | None) -> dict:
    request_id = f"{SIM_VERSION}:{item.worklist_item_id}:{seq}"
    return {
        "activity_id": str(uuid.uuid5(ACTIVITY_NAMESPACE, request_id)),
        "worklist_item_id": item.worklist_item_id,
        "client_request_id": request_id,
        "care_manager_email": item.care_manager_email,
        "activity_type": kind,
        "activity_ts": ts,
        "next_step_due_at": next_due,
    }


def plan_item(item: WorkItem) -> list[dict]:
    """Full outreach history for one item, ignoring the cutoff."""
    key = item.worklist_item_id
    if uniform(key, "attempted") < NOT_ATTEMPTED_RATE:
        return []
    sla_h = max((item.due_at - item.created_at).total_seconds() / 3600, 1.0)
    p_reach = REACH_PROBABILITY.get(item.risk_tier, min(REACH_PROBABILITY.values()))
    # First call inside the tier's SLA for most items; later calls 4-20 h apart.
    times = [item.created_at + timedelta(hours=0.5 + 0.8 * sla_h * uniform(key, "t", 1))]
    for n in range(2, MAX_ATTEMPTS + 1):
        times.append(times[-1] + timedelta(hours=4 + 16 * uniform(key, "t", n)))
    out: list[dict] = []
    for n, ts in enumerate(times, start=1):
        if uniform(key, "reach", n) < p_reach:
            kind = "DECLINED" if uniform(key, "decline") < DECLINE_RATE else "REACHED"
            out.append(_activity(item, n, kind, ts, None))
            booked = item.followup_booked_ts
            if kind == "REACHED" and booked is not None and booked >= ts:
                out.append(_activity(item, n + 1, "FOLLOWUP_BOOKED", booked, None))
            return out
        miss = "NO_ANSWER" if n % 2 else "LEFT_VOICEMAIL"
        out.append(_activity(item, n, miss, ts, times[n] if n < len(times) else None))
    out.append(_activity(item, MAX_ATTEMPTS + 1, "UNREACHABLE", times[-1] + timedelta(minutes=1), None))
    return out


def plan_activities(items: list[WorkItem], cutoff: datetime) -> list[dict]:
    return [a for item in items for a in plan_item(item) if a["activity_ts"] < cutoff]


def _utc(ts: datetime | None) -> datetime | None:
    """Spark returns naive datetimes in the session time zone, which get_spark sets to UTC."""
    return ts.replace(tzinfo=timezone.utc) if ts is not None and ts.tzinfo is None else ts


def load_items(spark, catalog: str, go_live, run_date) -> list[WorkItem]:
    rows = spark.sql(f"""
        SELECT w.worklist_item_id, w.assigned_care_manager, w.risk_tier, w.created_at, w.due_at,
               min(CASE WHEN f.booked_ts > w.created_at THEN f.booked_ts END) AS followup_booked_ts
        FROM {catalog}.readmission_worklist_gold.care_worklist w
        LEFT JOIN {catalog}.clinical_silver.follow_up_appointment f ON f.source_encounter_id = w.encounter_id
        WHERE w.assignment_status = 'ASSIGNED'
          AND w.worklist_date >= DATE'{go_live}' AND w.worklist_date < DATE'{run_date}'
        GROUP BY ALL""").collect()
    return [WorkItem(r.worklist_item_id, r.assigned_care_manager, r.risk_tier, _utc(r.created_at),
                     _utc(r.due_at), _utc(r.followup_booked_ts)) for r in rows]


INSERT_SQL = f"""
INSERT INTO {APP_SCHEMA}.outreach_activity
  (activity_id, worklist_item_id, client_request_id, care_manager_email, activity_type, activity_ts, next_step_due_at)
VALUES (%(activity_id)s, %(worklist_item_id)s, %(client_request_id)s, %(care_manager_email)s,
        %(activity_type)s, %(activity_ts)s, %(next_step_due_at)s)
ON CONFLICT (client_request_id) DO NOTHING"""


def write_activities(conn, activities: list[dict]) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {APP_SCHEMA}.outreach_activity")
        before = cur.fetchone()[0]
        for i in range(0, len(activities), INSERT_BATCH):
            cur.executemany(INSERT_SQL, activities[i:i + INSERT_BATCH])
            conn.commit()
        cur.execute(f"SELECT count(*) FROM {APP_SCHEMA}.outreach_activity")
        return cur.fetchone()[0] - before


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--go-live", required=True, type=lambda s: datetime.fromisoformat(s).date())
    p.add_argument("--run-date", default="", help="Simulate worklist days before this date; empty means today (UTC)")
    p.add_argument("--lakebase-project", required=True)
    p.add_argument("--lakebase-branch", required=True)
    p.add_argument("--lakebase-database", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    from collections import Counter

    from databricks.sdk import WorkspaceClient

    from readmit.common.spark import get_spark
    from readmit.lakebase.connect import LakebaseTarget, connect

    args = parse_args(argv)
    assert_environment(args.env, args.catalog, args.lakebase_project, args.lakebase_database)
    run_date = parse_or_today(args.run_date)
    cutoff = release_ts(run_date)
    items = load_items(get_spark(), args.catalog, args.go_live, run_date)
    activities = plan_activities(items, cutoff)
    w = WorkspaceClient()
    with connect(w, LakebaseTarget(args.lakebase_project, args.lakebase_branch, args.lakebase_database)) as conn:
        inserted = write_activities(conn, activities)
    reached = {a["worklist_item_id"] for a in activities if a["activity_type"] == "REACHED"}
    print(json.dumps({
        "run_date": run_date.isoformat(), "cutoff": cutoff.isoformat(), "assigned_items": len(items),
        "planned_activities": len(activities), "inserted": inserted,
        "by_type": dict(Counter(a["activity_type"] for a in activities)),
        "reach_rate": round(len(reached) / len(items), 3) if items else None,
    }, indent=2))


if __name__ == "__main__":
    main()
