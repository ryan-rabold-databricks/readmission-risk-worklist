"""DDL for the app-owned Postgres schema ``readmission_worklist_app`` (ERD v0.4).

Every statement is idempotent. Both tables are append-only from the app's point of
view and use REPLICA IDENTITY FULL, a Lakebase CDF requirement (DECISIONS.md #4).
Controlled values are enforced with CHECK constraints so bad writes fail at the
source rather than in the lakehouse.
"""

from __future__ import annotations

APP_SCHEMA = "readmission_worklist_app"
SYNCED_SCHEMA = "readmission_worklist_gold"
APP_TABLES = ("outreach_activity", "program_setting_change")

ACTIVITY_TYPES = ("NO_ANSWER", "LEFT_VOICEMAIL", "REACHED", "FOLLOWUP_BOOKED", "DECLINED", "UNREACHABLE")
SETTING_TYPES = ("RISK_TIER_POLICY", "CARE_TEAM_ASSIGNMENT", "CARE_MANAGER_CAPACITY")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def ddl_statements() -> list[str]:
    s = APP_SCHEMA
    return [
        f"CREATE SCHEMA IF NOT EXISTS {s}",
        f"""CREATE TABLE IF NOT EXISTS {s}.outreach_activity (
  activity_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  worklist_item_id   TEXT NOT NULL,
  client_request_id  TEXT NOT NULL UNIQUE,
  care_manager_email TEXT NOT NULL,
  activity_type      TEXT NOT NULL CHECK (activity_type IN ({_in(ACTIVITY_TYPES)})),
  activity_ts        TIMESTAMPTZ NOT NULL,
  next_step_due_at   TIMESTAMPTZ,
  note               TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        f"CREATE INDEX IF NOT EXISTS outreach_activity_item_idx ON {s}.outreach_activity (worklist_item_id, activity_ts)",
        f"""CREATE TABLE IF NOT EXISTS {s}.program_setting_change (
  change_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_request_id  TEXT NOT NULL UNIQUE,
  setting_type       TEXT NOT NULL CHECK (setting_type IN ({_in(SETTING_TYPES)})),
  target_key         TEXT NOT NULL,
  new_value_json     JSONB NOT NULL,
  change_reason      TEXT,
  effective_date     DATE NOT NULL,
  changed_by         TEXT NOT NULL,
  changed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
        *[f"ALTER TABLE {s}.{t} REPLICA IDENTITY FULL" for t in APP_TABLES],
    ]


REPLICA_IDENTITY_SQL = """
SELECT c.relname, c.relreplident
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relkind = 'r'
ORDER BY c.relname"""


def _role(app_role: str) -> str:
    return '"' + app_role.replace('"', '""') + '"'


def synced_read_grants(app_role: str) -> list[str]:
    """Read on the synced gold tables. Default privileges cannot cover them (they are
    created by the system role databricks_writer_<db oid>, DECISIONS.md #68), so
    publish_worklist re-applies these after every sync."""
    r = _role(app_role)
    return [
        f"GRANT USAGE ON SCHEMA {SYNCED_SCHEMA} TO {r}",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {SYNCED_SCHEMA} TO {r}",
    ]


def grant_statements(app_role: str) -> list[str]:
    """Least privilege for the app's service principal: read the synced gold tables,
    insert into (never update or delete) its own append-only tables."""
    r = _role(app_role)
    return [
        *synced_read_grants(app_role),
        f"GRANT USAGE ON SCHEMA {APP_SCHEMA} TO {r}",
        f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA {APP_SCHEMA} TO {r}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {APP_SCHEMA} GRANT SELECT, INSERT ON TABLES TO {r}",
    ]
