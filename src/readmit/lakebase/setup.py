"""<env>_readmit_setup: idempotent Lakebase setup the bundle cannot declare.

1. App schema readmission_worklist_app, its tables, CHECK constraints, and
   REPLICA IDENTITY FULL (verified after apply).
2. Lakebase CDF feed from that schema to <catalog>.readmission_worklist_app_bronze.
3. Optional (--app-role = the app service principal's client ID): Postgres grants on the
   synced and app schemas, and Unity Catalog grants on readmission_worklist_app_bronze
   so Databricks Apps telemetry can create and write the app_otel_* tables.

The project, database, and synced tables are bundle resources (DECISIONS.md #40).
"""

from __future__ import annotations

import argparse
import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import PermissionsChange, Privilege

from readmit.common.env_guardrail import assert_environment
from readmit.lakebase.app_schema import APP_SCHEMA, APP_TABLES, REPLICA_IDENTITY_SQL, ddl_statements, grant_statements
from readmit.lakebase.cdf import cdf_statuses, ensure_cdf_config
from readmit.lakebase.connect import LakebaseTarget, connect, database_resource_path


def apply_app_schema(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        for stmt in ddl_statements():
            cur.execute(stmt)
        cur.execute(REPLICA_IDENTITY_SQL, (APP_SCHEMA,))
        identity = {name: ident for name, ident in cur.fetchall()}
    conn.commit()
    wrong = {t: identity.get(t) for t in APP_TABLES if identity.get(t) != "f"}
    if wrong:
        raise RuntimeError(f"REPLICA IDENTITY FULL missing on {wrong}")
    return {t: "full" for t in APP_TABLES}


def apply_grants(conn, app_role: str) -> list[str]:
    stmts = grant_statements(app_role)
    with conn.cursor() as cur:
        for stmt in stmts:
            cur.execute(stmt)
    conn.commit()
    return stmts


# Telemetry export needs CREATE TABLE plus SELECT and MODIFY on the target schema
# (Apps observability docs); USE CATALOG comes from the catalog's existing grants.
TELEMETRY_SCHEMA = "readmission_worklist_app_bronze"
TELEMETRY_PRIVILEGES = (Privilege.USE_SCHEMA, Privilege.CREATE_TABLE, Privilege.SELECT, Privilege.MODIFY)


def apply_telemetry_grants(w: WorkspaceClient, catalog: str, app_sp: str) -> list[str]:
    """Additive: other principals' grants on the schema are left as they are."""
    full_name = f"{catalog}.{TELEMETRY_SCHEMA}"
    w.grants.update("schema", full_name, changes=[PermissionsChange(principal=app_sp, add=list(TELEMETRY_PRIVILEGES))])
    return [f"{p.value} ON SCHEMA {full_name} TO {app_sp}" for p in TELEMETRY_PRIVILEGES]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--lakebase-project", required=True)
    p.add_argument("--lakebase-branch", required=True)
    p.add_argument("--lakebase-database", required=True)
    p.add_argument("--app-role", default="", help="App service principal client ID (its Postgres role); empty skips grants")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog, args.lakebase_project, args.lakebase_database)
    w = WorkspaceClient()
    target = LakebaseTarget(args.lakebase_project, args.lakebase_branch, args.lakebase_database)
    db_path = database_resource_path(w, target)
    with connect(w, target) as conn:
        summary = {"database": db_path, "replica_identity": apply_app_schema(conn)}
        if args.app_role:
            summary["grants"] = apply_grants(conn, args.app_role)
    if args.app_role:
        summary["telemetry_grants"] = apply_telemetry_grants(w, args.catalog, args.app_role)
    cfg = ensure_cdf_config(w, db_path, args.catalog)
    summary["cdf_config"] = {"name": cfg.name, "postgres_schema": cfg.postgres_schema,
                             "destination": f"{cfg.catalog}.{cfg.schema}"}
    summary["cdf_statuses"] = cdf_statuses(w, cfg.name)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
