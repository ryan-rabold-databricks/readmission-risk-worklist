"""Gold tables written by jobs (not the pipeline). Created idempotently on every run.

care_worklist and care_team_roster enable change data feed (kept for downstream
incremental readers). Lakebase syncs the *_active views instead: the minimum necessary
for a care manager (DECISIONS.md #46), so Postgres never holds the full history of
names and phone numbers. Only primary keys are declared (DECISIONS.md #25).
"""

from __future__ import annotations

from pyspark.sql import SparkSession

from readmit.pipeline.audit import AUDIT_SCHEMA

GOLD = "readmission_worklist_gold"


def table(catalog: str, name: str) -> str:
    return f"{catalog}.{GOLD}.{name}"


def _ddl(catalog: str) -> dict[str, str]:
    return {
        "discharge_risk_score": f"""
CREATE TABLE IF NOT EXISTS {table(catalog, 'discharge_risk_score')} (
  score_id STRING NOT NULL COMMENT 'SHA-256(encounter_id, model_version, scoring_run_id)',
  encounter_id STRING NOT NULL,
  model_name STRING NOT NULL,
  model_version STRING NOT NULL,
  risk_score DOUBLE NOT NULL COMMENT 'Predicted probability of a non-elective readmission within 30 days',
  risk_tier STRING NOT NULL,
  top_drivers ARRAY<STRING> NOT NULL COMMENT 'Up to three risk-increasing drivers, plain language',
  worklist_date DATE NOT NULL COMMENT 'Morning the discharge is worked (discharge date + 1)',
  scored_at TIMESTAMP NOT NULL,
  scoring_run_id STRING NOT NULL COMMENT '<worklist_date>:v<model_version>, deterministic so reruns do not duplicate',
  {AUDIT_SCHEMA},
  CONSTRAINT discharge_risk_score_pk PRIMARY KEY (score_id)
)
CLUSTER BY (worklist_date)
COMMENT 'Append-only risk scores per discharge and model version'""",
        "care_worklist": f"""
CREATE TABLE IF NOT EXISTS {table(catalog, 'care_worklist')} (
  worklist_item_id STRING NOT NULL COMMENT 'SHA-256(encounter_id)',
  encounter_id STRING NOT NULL,
  score_id STRING NOT NULL,
  patient_id STRING NOT NULL,
  facility_id STRING NOT NULL,
  worklist_date DATE NOT NULL,
  assignment_status STRING NOT NULL COMMENT 'ASSIGNED or OVERFLOW (over capacity, unassigned)',
  assigned_care_manager STRING COMMENT 'NULL when assignment_status = OVERFLOW',
  patient_display_name STRING NOT NULL,
  phone STRING,
  risk_score DOUBLE NOT NULL,
  risk_tier STRING NOT NULL,
  top_drivers ARRAY<STRING> NOT NULL,
  outreach_brief STRING COMMENT 'ai_query draft; generated for recent worklist days only',
  due_at TIMESTAMP NOT NULL COMMENT 'created_at + outreach SLA of the risk tier',
  created_at TIMESTAMP NOT NULL COMMENT 'When the item was released to the worklist',
  {AUDIT_SCHEMA},
  CONSTRAINT care_worklist_pk PRIMARY KEY (worklist_item_id)
)
CLUSTER BY (worklist_date, facility_id)
COMMENT 'Prioritized outreach worklist, one item per high- or medium-risk discharge'
TBLPROPERTIES (delta.enableChangeDataFeed = true)""",
        "care_team_roster": f"""
CREATE TABLE IF NOT EXISTS {table(catalog, 'care_team_roster')} (
  roster_id STRING NOT NULL COMMENT 'SHA-256(care_manager_email, facility_id, roster_date)',
  care_manager_email STRING NOT NULL,
  facility_id STRING NOT NULL,
  roster_date DATE NOT NULL,
  daily_capacity INT NOT NULL COMMENT 'Per care manager per day, across all of their facilities',
  {AUDIT_SCHEMA},
  CONSTRAINT care_team_roster_pk PRIMARY KEY (roster_id)
)
CLUSTER BY (roster_date)
COMMENT 'Care managers who can act on each facility''s worklist on a given day'
TBLPROPERTIES (delta.enableChangeDataFeed = true)""",
    }


# Worklist days kept in Lakebase: the 30-day readmission window a care manager may
# still be following up in.
ACTIVE_WINDOW_DAYS = 30

# Columns a care manager needs to make and log the call; internal keys (encounter,
# patient, score) and audit columns stay in the lakehouse.
CARE_WORKLIST_ACTIVE_COLUMNS = (
    "worklist_item_id", "facility_id", "worklist_date", "assignment_status", "assigned_care_manager",
    "patient_display_name", "phone", "risk_score", "risk_tier", "top_drivers", "outreach_brief",
    "due_at", "created_at",
)
CARE_TEAM_ROSTER_ACTIVE_COLUMNS = ("roster_id", "care_manager_email", "facility_id", "roster_date", "daily_capacity")


def _view_ddl(catalog: str, window_days: int) -> dict[str, str]:
    """The window is relative to the latest built day (not the wall clock), so the views
    are reproducible and still work during a backfill."""
    def view(name: str, source: str, cols: tuple[str, ...], date_col: str, comment: str) -> str:
        return f"""
CREATE OR REPLACE VIEW {table(catalog, name)}
COMMENT '{comment}'
AS SELECT {", ".join(cols)}
FROM {table(catalog, source)}
WHERE {date_col} > (SELECT max({date_col}) FROM {table(catalog, source)}) - INTERVAL {int(window_days)} DAYS"""

    return {
        "care_worklist_active": view(
            "care_worklist_active", "care_worklist", CARE_WORKLIST_ACTIVE_COLUMNS, "worklist_date",
            f"Lakebase sync source: care-manager columns for the latest {window_days} worklist days"),
        "care_team_roster_active": view(
            "care_team_roster_active", "care_team_roster", CARE_TEAM_ROSTER_ACTIVE_COLUMNS, "roster_date",
            f"Lakebase sync source: roster for the latest {window_days} worklist days"),
    }


def ensure_tables(spark: SparkSession, catalog: str, window_days: int = ACTIVE_WINDOW_DAYS) -> None:
    for ddl in _ddl(catalog).values():
        spark.sql(ddl)
    for ddl in _view_ddl(catalog, window_days).values():
        spark.sql(ddl)
