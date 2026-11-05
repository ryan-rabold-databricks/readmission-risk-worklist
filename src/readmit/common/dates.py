"""Date helpers shared by the daily cycle and the program backfill."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def parse_or_today(raw: str) -> date:
    return date.fromisoformat(raw) if raw else today_utc()


def date_range(start: date, end: date) -> list[date]:
    """Inclusive range; empty when end < start."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def release_ts(worklist_date: date) -> datetime:
    """When a worklist day is released to care managers: 12:00 UTC (07:00 US Central)."""
    return datetime(worklist_date.year, worklist_date.month, worklist_date.day, 12, tzinfo=timezone.utc)


def month_starts(go_live: date, run_date: date) -> list[date]:
    """First day of each month from go_live (itself, if mid-month) through run_date."""
    starts, m = [], date(go_live.year, go_live.month, 1)
    while m <= run_date:
        starts.append(max(m, go_live))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return starts
