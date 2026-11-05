"""Lakebase CDF feed: app schema -> <catalog>.readmission_worklist_app_bronze.

One feed per Postgres schema; each table lands as lb_<table>_history. The synced
gold schema must never get a feed (project CLAUDE.md), so it is refused here.
"""

from __future__ import annotations

import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.postgres import CdfConfig

from readmit.lakebase.app_schema import APP_SCHEMA, SYNCED_SCHEMA

CDF_DESTINATION_SCHEMA = "readmission_worklist_app_bronze"
CDF_CONFIG_ID = "readmission-worklist-app"
FORBIDDEN_SOURCE_SCHEMAS = {SYNCED_SCHEMA}


def ensure_cdf_config(w: WorkspaceClient, database_path: str, catalog: str,
                      postgres_schema: str = APP_SCHEMA) -> CdfConfig:
    if postgres_schema in FORBIDDEN_SOURCE_SCHEMAS:
        raise ValueError(f"Refusing to start a CDF feed on Postgres schema '{postgres_schema}'")
    try:
        existing = list(w.postgres.list_cdf_configs(parent=database_path))
    except NotFound:  # the API returns 404 when no config exists
        existing = []
    for cfg in existing:
        if cfg.postgres_schema == postgres_schema:
            if (cfg.catalog, cfg.schema) != (catalog, CDF_DESTINATION_SCHEMA):
                raise RuntimeError(
                    f"CDF config {cfg.name} sends {postgres_schema} to {cfg.catalog}.{cfg.schema}, "
                    f"expected {catalog}.{CDF_DESTINATION_SCHEMA}; configs are immutable, fix by hand")
            return cfg
    return w.postgres.create_cdf_config(
        parent=database_path,
        cdf_config=CdfConfig(catalog=catalog, schema=CDF_DESTINATION_SCHEMA, postgres_schema=postgres_schema),
        cdf_config_id=CDF_CONFIG_ID,
    ).wait()


def cdf_statuses(w: WorkspaceClient, database_path: str) -> list[dict]:
    try:
        statuses = list(w.postgres.list_cdf_statuses(parent=database_path))
    except NotFound:
        return []
    return [{"postgres_table": s.postgres_table, "uc_table": s.uc_table,
             "state": str(s.state).rsplit(".", 1)[-1] if s.state else None,
             "last_sync_time": str(s.last_sync_time) if s.last_sync_time else None,
             "detail": s.status_detail} for s in statuses]


def wait_for_streaming(w: WorkspaceClient, database_path: str, tables: set[str], timeout_s: int = 900) -> list[dict]:
    """Wait until every named table streams. Tables with no rows are skipped by CDF
    until their first row, so callers pass only non-empty tables."""
    deadline = time.time() + timeout_s
    while True:
        statuses = cdf_statuses(w, database_path)
        streaming = {s["postgres_table"].rsplit(".", 1)[-1] for s in statuses
                     if s["postgres_table"] and s["state"] == "CDF_STATE_STREAMING"}
        if tables <= streaming or time.time() > deadline:
            return statuses
        time.sleep(15)
