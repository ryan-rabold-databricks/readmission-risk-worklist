"""Connect to the Lakebase primary endpoint as the job's own identity (OAuth token).

The Postgres role of a Databricks user is their email and the role of a service
principal is its application ID; both equal ``current_user.me().user_name``. Tokens
last an hour, so every connection fetches a fresh one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from databricks.sdk import WorkspaceClient

# A scaled-to-zero endpoint wakes on the first connection; retry briefly.
CONNECT_ATTEMPTS = 5
CONNECT_BACKOFF_SECONDS = 3


@dataclass(frozen=True)
class LakebaseTarget:
    project: str
    branch: str
    database: str  # Postgres database name (underscores)

    @property
    def branch_path(self) -> str:
        return f"projects/{self.project}/branches/{self.branch}"


def read_write_endpoint(w: WorkspaceClient, target: LakebaseTarget):
    endpoints = [e for e in w.postgres.list_endpoints(parent=target.branch_path)
                 if e.status and str(e.status.endpoint_type).endswith("READ_WRITE")]
    if len(endpoints) != 1:
        raise RuntimeError(f"Expected one read-write endpoint on {target.branch_path}, found {len(endpoints)}")
    return endpoints[0]


def database_resource_path(w: WorkspaceClient, target: LakebaseTarget) -> str:
    """Resource path of the database whose Postgres name is target.database."""
    for db in w.postgres.list_databases(parent=target.branch_path):
        if db.status and db.status.postgres_database == target.database:
            return db.name
    raise RuntimeError(f"Postgres database '{target.database}' not found on {target.branch_path}; deploy the bundle first")


def connect(w: WorkspaceClient, target: LakebaseTarget, autocommit: bool = False):
    import psycopg

    endpoint = read_write_endpoint(w, target)
    host = endpoint.status.hosts.host
    user = w.current_user.me().user_name
    last_error: Exception | None = None
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        token = w.postgres.generate_database_credential(endpoint=endpoint.name).token
        try:
            return psycopg.connect(host=host, dbname=target.database, user=user, password=token,
                                   sslmode="require", autocommit=autocommit, connect_timeout=30,
                                   application_name="readmit")
        except psycopg.OperationalError as e:  # endpoint waking from scale-to-zero
            last_error = e
            time.sleep(CONNECT_BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"Could not connect to {host}/{target.database} as {user}") from last_error
