"""C11: why publish_worklist re-grants synced-table reads instead of using default privileges (DECISIONS.md #68).

Connects to Lakebase as the deploying role (the author in dev) and, inside one transaction that is
always rolled back, attempts the two alternatives #68 rejected. Each attempt runs in a savepoint so
the refusal text is captured; nothing is committed. Also records who owns the synced tables and
whether the app role can read them today (read-only catalog queries).

Usage (author, local):
  DATABRICKS_CONFIG_PROFILE=fevm-classic-stable PYTHONPATH=src uv run --no-project --python 3.12 \
    --with "databricks-sdk>=0.81.0" --with "psycopg[binary]>=3.2,<3.3" \
    python evidence/phase7/c11_lakebase_privilege_check.py > evidence/phase7/c11_lakebase_privilege_check.txt
"""
import datetime

from databricks.sdk import WorkspaceClient

from readmit.lakebase.connect import LakebaseTarget, connect

TARGET = LakebaseTarget(project="readmission-worklist", branch="production", database="readmission_worklist")
APP_ROLE = "c21146c6-b973-4b42-a0cb-6cc41e5e777c"  # dev app service principal (phase5/setup_app_grants.log)

w = WorkspaceClient()
print(f"# C11 run {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ} as {w.current_user.me().user_name}; "
      f"{TARGET.branch_path}, database {TARGET.database}. One transaction, always rolled back.")

with connect(w, TARGET) as conn, conn.cursor() as cur:
    def show(title, sql, params=None):
        cur.execute(sql, params)
        print(f"\n### {title}\n{sql}")
        print([d.name for d in cur.description])
        for row in cur.fetchall():
            print(row)

    show("Connected role, database oid", "SELECT current_user, current_database(), (SELECT oid FROM pg_database WHERE datname = current_database())")
    show("Owners of the synced tables",
         "SELECT schemaname, tablename, tableowner FROM pg_tables WHERE schemaname = 'readmission_worklist_gold' ORDER BY 2")
    show("Built-in databricks_* roles in this database",
         "SELECT rolname FROM pg_roles WHERE rolname LIKE 'databricks_writer_%%' OR rolname LIKE 'databricks_reader_%%' ORDER BY 1")
    show("App role can read each synced table today (after publish_worklist re-grants, #68)",
         "SELECT c.relname, has_table_privilege(%s, c.oid, 'SELECT') app_can_select "
         "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
         "WHERE n.nspname = 'readmission_worklist_gold' AND c.relkind IN ('r', 'p') ORDER BY 1", (APP_ROLE,))

    cur.execute("SELECT tableowner FROM pg_tables WHERE schemaname = 'readmission_worklist_gold' LIMIT 1")
    writer = cur.fetchone()[0]
    cur.execute("SELECT oid FROM pg_database WHERE datname = current_database()")
    reader = f"databricks_reader_{cur.fetchone()[0]}"

    attempts = [
        ("Alternative 1: default privileges for the synced-table owner",
         f'ALTER DEFAULT PRIVILEGES FOR ROLE "{writer}" IN SCHEMA readmission_worklist_gold GRANT SELECT ON TABLES TO "{APP_ROLE}"'),
        ("Alternative 2: grant the app role the built-in reader role",
         f'GRANT "{reader}" TO "{APP_ROLE}"'),
    ]
    for title, sql in attempts:
        cur.execute("SAVEPOINT attempt")
        print(f"\n### {title}\n{sql}")
        try:
            cur.execute(sql)
            print("ACCEPTED (will be rolled back)")
        except Exception as e:  # the refusal is the evidence
            print(f"REFUSED: {type(e).__name__}: {str(e).strip()}")
        cur.execute("ROLLBACK TO SAVEPOINT attempt")

    conn.rollback()
    print("\n### Transaction rolled back; nothing committed")
