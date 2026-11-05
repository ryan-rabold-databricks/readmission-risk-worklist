"""Lakebase CDF feed: app schema -> <catalog>.readmission_worklist_app_bronze.

One feed per Postgres schema; each table lands as lb_<table>_history. The synced
gold schema must never get a feed (project CLAUDE.md), so it is refused here.
"""

from __future__ import annotations

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.postgres import CdfConfig

from readmit.lakebase.app_schema import APP_SCHEMA, SYNCED_SCHEMA

CDF_DESTINATION_SCHEMA = "readmission_worklist_app_bronze"
CDF_CONFIG_ID = "readmission_worklist_app"  # [a-z][a-z0-9_]{0,62}
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


def cdf_statuses(w: WorkspaceClient, cdf_config_name: str) -> list[dict]:
    """Per-table feed status. The parent is the CDF config path, not the database path."""
    try:
        statuses = list(w.postgres.list_cdf_statuses(parent=cdf_config_name))
    except NotFound:
        return []
    return [{"postgres_table": s.postgres_table, "uc_table": s.uc_table,
             "state": s.state.value if s.state else None,
             "last_sync_time": str(s.last_sync_time) if s.last_sync_time else None,
             "detail": s.status_detail} for s in statuses]
