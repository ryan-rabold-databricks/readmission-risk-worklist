from datetime import datetime, timedelta, timezone

import pytest

from readmit.lakebase.app_schema import ACTIVITY_TYPES, APP_TABLES, ddl_statements, grant_statements
from readmit.lakebase.cdf import ensure_cdf_config
from readmit.lakebase.outreach_sim import WorkItem, plan_activities, plan_item

T0 = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)


def item(i: int, tier: str = "HIGH", booked: datetime | None = None) -> WorkItem:
    sla = 24 if tier == "HIGH" else 72
    return WorkItem(f"item{i}", "cm@example.org", tier, T0, T0 + timedelta(hours=sla), booked)


def test_every_app_table_gets_replica_identity_full():
    stmts = ddl_statements()
    for t in APP_TABLES:
        assert any(s == f"ALTER TABLE readmission_worklist_app.{t} REPLICA IDENTITY FULL" for s in stmts)
    assert all("IF NOT EXISTS" in s or "REPLICA IDENTITY" in s for s in stmts)


def test_app_grants_are_insert_only_on_app_schema():
    stmts = grant_statements('app"sp')
    assert '"app""sp"' in stmts[0]
    assert not any(word in s for s in stmts for word in ("UPDATE", "DELETE", "TRUNCATE"))


def test_cdf_feed_on_synced_gold_schema_is_refused():
    with pytest.raises(ValueError, match="Refusing"):
        ensure_cdf_config(None, "projects/p/branches/b/databases/d", "cat", postgres_schema="readmission_worklist_gold")


def test_plan_is_deterministic_and_well_formed():
    items = [item(i, "HIGH" if i % 2 else "MEDIUM") for i in range(500)]
    a, b = plan_activities(items, T0 + timedelta(days=30)), plan_activities(items, T0 + timedelta(days=30))
    assert a == b
    assert len({x["client_request_id"] for x in a}) == len(a)
    assert {x["activity_type"] for x in a} <= set(ACTIVITY_TYPES)
    for x in a:
        assert x["activity_ts"] > T0
        assert "note" not in x  # note stays NULL: IDs only, no free text


def test_reach_rate_is_plausible():
    items = [item(i) for i in range(2000)]
    acts = plan_activities(items, T0 + timedelta(days=30))
    reached = {x["worklist_item_id"] for x in acts if x["activity_type"] == "REACHED"}
    assert 0.55 < len(reached) / len(items) < 0.75


def test_followup_booked_only_after_reach_and_when_ehr_shows_booking():
    no_booking = [x for i in range(300) for x in plan_item(item(i))]
    assert not any(x["activity_type"] == "FOLLOWUP_BOOKED" for x in no_booking)
    booked = [x for i in range(300) for x in plan_item(item(i, booked=T0 + timedelta(days=5)))]
    assert any(x["activity_type"] == "FOLLOWUP_BOOKED" for x in booked)


def test_cutoff_drops_future_activities_and_reruns_extend():
    items = [item(i) for i in range(200)]
    early = plan_activities(items, T0 + timedelta(hours=6))
    late = plan_activities(items, T0 + timedelta(days=5))
    assert all(x["activity_ts"] < T0 + timedelta(hours=6) for x in early)
    assert {x["client_request_id"] for x in early} < {x["client_request_id"] for x in late}
