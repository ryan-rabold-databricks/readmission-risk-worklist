"""Program Settings changes from the app, validated and applied on top of the seeds.

The app appends rows to Lakebase ``readmission_worklist_app.program_setting_change``;
Lakebase CDF lands them in ``lb_program_setting_change_history``. The pipeline
re-validates every change (the app validates too, but the lakehouse does not trust it)
and turns the seeds plus applied changes into effective-dated versions of
risk_tier_policy, care_team_assignment, and care_manager_capacity.

Change shapes (``new_value_json``), one coherent value per change:
- RISK_TIER_POLICY, target_key ``ALL``: {"tiers": [{"risk_tier", "min_score", "max_score",
  "outreach_sla_hours", "include_in_worklist"}, ...]}, exactly HIGH, MEDIUM, LOW,
  covering 0-1 without gaps in LOW < MEDIUM < HIGH order.
- CARE_TEAM_ASSIGNMENT, target_key = care manager email: {"facility_ids": [...]}, the
  full set of facilities they cover from effective_date (empty = none).
- CARE_MANAGER_CAPACITY, target_key = care manager email: {"daily_capacity": n}.

A change applies from its effective_date, which may not be before the day it was made
(no retroactive changes: worklists already released are never rebuilt). Changes for
the same key apply in (effective_date, changed_at) order; a later change on the same
effective_date supersedes an earlier one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

RISK_TIER_POLICY = "RISK_TIER_POLICY"
CARE_TEAM_ASSIGNMENT = "CARE_TEAM_ASSIGNMENT"
CARE_MANAGER_CAPACITY = "CARE_MANAGER_CAPACITY"

APPLIED = "APPLIED"
REJECTED = "REJECTED"
SUPERSEDED = "SUPERSEDED"

TIERS_LOW_TO_HIGH = ("LOW", "MEDIUM", "HIGH")
MAX_DAILY_CAPACITY = 500
MAX_SLA_HOURS = 24 * 14
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Change:
    change_id: str
    setting_type: str
    target_key: str
    new_value_json: str
    effective_date: date
    changed_by: str
    changed_at: datetime


@dataclass
class Validated:
    change: Change
    status: str
    status_reason: str | None = None
    value: dict = field(default_factory=dict)


def _tier_policy(value: dict) -> dict:
    tiers = value.get("tiers")
    if not isinstance(tiers, list) or sorted(t.get("risk_tier") for t in tiers if isinstance(t, dict)) != sorted(TIERS_LOW_TO_HIGH):
        raise ValueError("tiers must list HIGH, MEDIUM, and LOW exactly once")
    by_tier = {t["risk_tier"]: t for t in tiers}
    clean = []
    for name in TIERS_LOW_TO_HIGH:
        t = by_tier[name]
        lo, hi, sla, include = t.get("min_score"), t.get("max_score"), t.get("outreach_sla_hours"), t.get("include_in_worklist")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (lo, hi)) or not 0 <= lo < hi <= 1:
            raise ValueError(f"{name}: scores must satisfy 0 <= min_score < max_score <= 1")
        if not isinstance(sla, int) or isinstance(sla, bool) or not 1 <= sla <= MAX_SLA_HOURS:
            raise ValueError(f"{name}: outreach_sla_hours must be an integer from 1 to {MAX_SLA_HOURS}")
        if not isinstance(include, bool):
            raise ValueError(f"{name}: include_in_worklist must be true or false")
        clean.append({"risk_tier": name, "min_score": float(lo), "max_score": float(hi),
                      "outreach_sla_hours": sla, "include_in_worklist": include})
    if clean[0]["min_score"] != 0 or clean[-1]["max_score"] != 1:
        raise ValueError("tiers must cover scores from 0 to 1")
    for lower, upper in zip(clean, clean[1:]):
        if lower["max_score"] != upper["min_score"]:
            raise ValueError(f"{lower['risk_tier']} max_score must equal {upper['risk_tier']} min_score")
    return {"tiers": clean}


def _assignment(value: dict, facilities: set[str]) -> dict:
    ids = value.get("facility_ids")
    if not isinstance(ids, list) or not all(isinstance(f, str) for f in ids):
        raise ValueError("facility_ids must be a list of facility IDs")
    unknown = sorted(set(ids) - facilities)
    if unknown:
        raise ValueError(f"unknown facility_ids: {', '.join(unknown)}")
    return {"facility_ids": sorted(set(ids))}


def _capacity(value: dict) -> dict:
    n = value.get("daily_capacity")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_DAILY_CAPACITY:
        raise ValueError(f"daily_capacity must be an integer from 1 to {MAX_DAILY_CAPACITY}")
    return {"daily_capacity": n}


def validate(change: Change, facilities: set[str]) -> Validated:
    try:
        if change.effective_date < change.changed_at.date():
            raise ValueError("effective_date is before the change was made")
        value = json.loads(change.new_value_json)
        if not isinstance(value, dict):
            raise ValueError("new_value_json must be a JSON object")
        if change.setting_type == RISK_TIER_POLICY:
            if change.target_key != "ALL":
                raise ValueError("RISK_TIER_POLICY target_key must be ALL")
            clean = _tier_policy(value)
        elif change.setting_type in (CARE_TEAM_ASSIGNMENT, CARE_MANAGER_CAPACITY):
            if not _EMAIL.match(change.target_key) or change.target_key != change.target_key.lower():
                raise ValueError("target_key must be a lowercase care manager email")
            clean = _assignment(value, facilities) if change.setting_type == CARE_TEAM_ASSIGNMENT else _capacity(value)
        else:
            raise ValueError(f"unknown setting_type {change.setting_type}")
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        return Validated(change, REJECTED, str(e))
    return Validated(change, APPLIED, None, clean)


def validate_all(changes: list[Change], facilities: set[str]) -> list[Validated]:
    """Validate every change, then mark an applied change SUPERSEDED when a later one
    for the same setting and key has the same effective_date."""
    results = [validate(c, facilities) for c in changes]
    last: dict[tuple[str, str, date], Validated] = {}
    for v in sorted((v for v in results if v.status == APPLIED), key=lambda v: (v.change.changed_at, v.change.change_id)):
        k = (v.change.setting_type, v.change.target_key, v.change.effective_date)
        if k in last:
            last[k].status, last[k].status_reason = SUPERSEDED, f"superseded by {v.change.change_id}"
        last[k] = v
    return results


def apply_versions(base: list[dict], changes: list[Validated], key_of, rows_of) -> list[dict]:
    """Effective-dated rows: ``base`` (seed rows with effective_date / expiration_date)
    with each applied change replacing its key's rows from its effective_date on.

    key_of(row) gives a row's setting key; rows_of(validated) gives the new rows for a
    change, each with the change's effective_date and no expiration. Every row keeps a
    ``change_id`` (None for seed rows).
    """
    rows = [dict(r, change_id=None) for r in base]
    for v in sorted((v for v in changes if v.status == APPLIED), key=lambda v: (v.change.effective_date, v.change.changed_at, v.change.change_id)):
        d, key = v.change.effective_date, v.change.target_key
        kept = []
        for r in rows:
            if key_of(r) == key:
                if r["effective_date"] >= d:
                    continue
                if r["expiration_date"] is None or r["expiration_date"] > d:
                    r = dict(r, expiration_date=d)
            kept.append(r)
        rows = kept + [dict(r, effective_date=d, expiration_date=None, change_id=v.change.change_id) for r in rows_of(v)]
    return rows


def tier_policy_rows(base: list[dict], changes: list[Validated]) -> list[dict]:
    return apply_versions(
        base, [v for v in changes if v.change.setting_type == RISK_TIER_POLICY],
        key_of=lambda r: "ALL",
        rows_of=lambda v: [dict(t, is_active=True) for t in v.value["tiers"]],
    )


def assignment_rows(base: list[dict], changes: list[Validated]) -> list[dict]:
    return apply_versions(
        base, [v for v in changes if v.change.setting_type == CARE_TEAM_ASSIGNMENT],
        key_of=lambda r: r["care_manager_email"],
        rows_of=lambda v: [{"care_manager_email": v.change.target_key, "facility_id": f} for f in v.value["facility_ids"]],
    )


def capacity_rows(base: list[dict], changes: list[Validated]) -> list[dict]:
    return apply_versions(
        base, [v for v in changes if v.change.setting_type == CARE_MANAGER_CAPACITY],
        key_of=lambda r: r["care_manager_email"],
        rows_of=lambda v: [{"care_manager_email": v.change.target_key, "daily_capacity": v.value["daily_capacity"]}],
    )
