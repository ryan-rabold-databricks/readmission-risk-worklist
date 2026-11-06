import json
from datetime import date, datetime

from readmit.pipeline import program_settings as ps

FACILITIES = {"FAC-A", "FAC-B", "FAC-C"}
CM = "cm@example.org"


def change(setting_type, value, target="ALL", eff=date(2026, 11, 10), at=datetime(2026, 11, 7, 9), cid="c1"):
    return ps.Change(cid, setting_type, target, json.dumps(value), eff, "lead@example.org", at)


def tiers(high_min=0.30, med_min=0.18, high_sla=24):
    return {"tiers": [
        {"risk_tier": "HIGH", "min_score": high_min, "max_score": 1.0, "outreach_sla_hours": high_sla, "include_in_worklist": True},
        {"risk_tier": "MEDIUM", "min_score": med_min, "max_score": high_min, "outreach_sla_hours": 72, "include_in_worklist": True},
        {"risk_tier": "LOW", "min_score": 0.0, "max_score": med_min, "outreach_sla_hours": 168, "include_in_worklist": False},
    ]}


def test_valid_tier_policy_applies():
    v = ps.validate(change(ps.RISK_TIER_POLICY, tiers(0.35)), FACILITIES)
    assert v.status == ps.APPLIED
    assert [t["risk_tier"] for t in v.value["tiers"]] == ["LOW", "MEDIUM", "HIGH"]


def test_tier_policy_with_gap_is_rejected():
    bad = tiers()
    bad["tiers"][1]["max_score"] = 0.29
    v = ps.validate(change(ps.RISK_TIER_POLICY, bad), FACILITIES)
    assert v.status == ps.REJECTED and "MEDIUM max_score" in v.status_reason


def test_tier_policy_rejects_bad_types_and_missing_tier():
    bad = tiers()
    bad["tiers"][0]["outreach_sla_hours"] = 24.5
    assert ps.validate(change(ps.RISK_TIER_POLICY, bad), FACILITIES).status == ps.REJECTED
    assert ps.validate(change(ps.RISK_TIER_POLICY, {"tiers": tiers()["tiers"][:2]}), FACILITIES).status == ps.REJECTED
    assert ps.validate(change(ps.RISK_TIER_POLICY, tiers(), target="HIGH"), FACILITIES).status == ps.REJECTED


def test_retroactive_change_is_rejected():
    v = ps.validate(change(ps.CARE_MANAGER_CAPACITY, {"daily_capacity": 40}, target=CM, eff=date(2026, 11, 6)), FACILITIES)
    assert v.status == ps.REJECTED and "before" in v.status_reason


def test_same_day_effective_change_is_allowed():
    v = ps.validate(change(ps.CARE_MANAGER_CAPACITY, {"daily_capacity": 40}, target=CM, eff=date(2026, 11, 7)), FACILITIES)
    assert v.status == ps.APPLIED


def test_assignment_and_capacity_validation():
    assert ps.validate(change(ps.CARE_TEAM_ASSIGNMENT, {"facility_ids": ["FAC-X"]}, target=CM), FACILITIES).status == ps.REJECTED
    assert ps.validate(change(ps.CARE_TEAM_ASSIGNMENT, {"facility_ids": []}, target=CM), FACILITIES).status == ps.APPLIED
    assert ps.validate(change(ps.CARE_TEAM_ASSIGNMENT, {"facility_ids": ["FAC-A"]}, target="CM@Example.org"), FACILITIES).status == ps.REJECTED
    assert ps.validate(change(ps.CARE_MANAGER_CAPACITY, {"daily_capacity": 0}, target=CM), FACILITIES).status == ps.REJECTED
    assert ps.validate(change(ps.CARE_MANAGER_CAPACITY, {"daily_capacity": True}, target=CM), FACILITIES).status == ps.REJECTED
    assert ps.validate(ps.Change("c", ps.CARE_MANAGER_CAPACITY, CM, "not json", date(2026, 11, 10), "x", datetime(2026, 11, 7)),
                       FACILITIES).status == ps.REJECTED


def test_later_change_same_effective_date_supersedes():
    a = change(ps.CARE_MANAGER_CAPACITY, {"daily_capacity": 40}, target=CM, cid="a", at=datetime(2026, 11, 7, 9))
    b = change(ps.CARE_MANAGER_CAPACITY, {"daily_capacity": 45}, target=CM, cid="b", at=datetime(2026, 11, 7, 10))
    va, vb = ps.validate_all([a, b], FACILITIES)
    assert (va.status, vb.status) == (ps.SUPERSEDED, ps.APPLIED)
    rows = ps.capacity_rows(_capacity_seed(), [va, vb])
    future = [r for r in rows if r["effective_date"] == date(2026, 11, 10)]
    assert [r["daily_capacity"] for r in future] == [45]


def _capacity_seed():
    return [{"care_manager_email": CM, "daily_capacity": 50, "effective_date": date(2024, 11, 1), "expiration_date": None}]


def test_capacity_change_expires_seed_row():
    rows = ps.capacity_rows(_capacity_seed(), ps.validate_all(
        [change(ps.CARE_MANAGER_CAPACITY, {"daily_capacity": 40}, target=CM)], FACILITIES))
    assert rows == [
        {"care_manager_email": CM, "daily_capacity": 50, "effective_date": date(2024, 11, 1), "expiration_date": date(2026, 11, 10), "change_id": None},
        {"care_manager_email": CM, "daily_capacity": 40, "effective_date": date(2026, 11, 10), "expiration_date": None, "change_id": "c1"},
    ]


def test_assignment_change_replaces_facility_set_and_chains():
    seed = [
        {"care_manager_email": CM, "facility_id": f, "effective_date": date(2024, 11, 1), "expiration_date": None}
        for f in ("FAC-A", "FAC-B")
    ] + [{"care_manager_email": "other@example.org", "facility_id": "FAC-C", "effective_date": date(2024, 11, 1), "expiration_date": None}]
    first = change(ps.CARE_TEAM_ASSIGNMENT, {"facility_ids": ["FAC-B", "FAC-C"]}, target=CM, cid="first")
    second = change(ps.CARE_TEAM_ASSIGNMENT, {"facility_ids": []}, target=CM, cid="second",
                    eff=date(2026, 12, 1), at=datetime(2026, 11, 8))
    rows = ps.assignment_rows(seed, ps.validate_all([first, second], FACILITIES))

    def active(d):
        return sorted((r["care_manager_email"], r["facility_id"]) for r in rows
                      if r["effective_date"] <= d and (r["expiration_date"] is None or r["expiration_date"] > d))

    assert active(date(2026, 11, 9)) == [(CM, "FAC-A"), (CM, "FAC-B"), ("other@example.org", "FAC-C")]
    assert active(date(2026, 11, 10)) == [(CM, "FAC-B"), (CM, "FAC-C"), ("other@example.org", "FAC-C")]
    assert active(date(2026, 12, 1)) == [("other@example.org", "FAC-C")]


def test_tier_policy_versions():
    seed = [dict(t, is_active=True, effective_date=date(2024, 11, 1), expiration_date=None) for t in tiers()["tiers"]]
    rows = ps.tier_policy_rows(seed, ps.validate_all([change(ps.RISK_TIER_POLICY, tiers(0.35))], FACILITIES))
    old = [r for r in rows if r["change_id"] is None]
    new = [r for r in rows if r["change_id"] == "c1"]
    assert len(old) == len(new) == 3
    assert all(r["expiration_date"] == date(2026, 11, 10) for r in old)
    assert {r["risk_tier"]: r["min_score"] for r in new}["HIGH"] == 0.35
