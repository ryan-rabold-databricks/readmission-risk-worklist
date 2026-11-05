"""Capacity-capped routing of one day's worklist items (DECISIONS.md #29).

Items are taken highest risk first. Each goes to the eligible care manager (rostered
at the item's facility that day) with the most remaining capacity; ties break by
email. When no eligible care manager has capacity left, the item is OVERFLOW: visible
on the worklist but unassigned.
"""

from __future__ import annotations

from dataclasses import dataclass

ASSIGNED = "ASSIGNED"
OVERFLOW = "OVERFLOW"


@dataclass(frozen=True)
class Assignment:
    worklist_item_id: str
    care_manager_email: str | None
    status: str


def assign_items(items: list[dict], roster: list[dict]) -> list[Assignment]:
    """items: worklist_item_id, facility_id, risk_score.
    roster: care_manager_email, facility_id, daily_capacity (per person, repeated per facility)."""
    remaining: dict[str, int] = {}
    by_facility: dict[str, list[str]] = {}
    for r in roster:
        remaining[r["care_manager_email"]] = int(r["daily_capacity"])
        by_facility.setdefault(r["facility_id"], []).append(r["care_manager_email"])

    result = []
    for item in sorted(items, key=lambda i: (-float(i["risk_score"]), i["worklist_item_id"])):
        eligible = [cm for cm in by_facility.get(item["facility_id"], []) if remaining[cm] > 0]
        if not eligible:
            result.append(Assignment(item["worklist_item_id"], None, OVERFLOW))
            continue
        chosen = min(eligible, key=lambda cm: (-remaining[cm], cm))
        remaining[chosen] -= 1
        result.append(Assignment(item["worklist_item_id"], chosen, ASSIGNED))
    return result
