"""Environment guardrail.

Every job calls ``assert_environment`` before touching data. A run is rejected when
its catalog or Lakebase project does not match the values configured for its
environment, so a parameter override can never point a dev run at prod data (or the
reverse). Keep ``ENVIRONMENTS`` in step with the targets in ``databricks.yml``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Environment:
    name: str
    catalog: str
    lakebase_project: str
    lakebase_database: str


ENVIRONMENTS: dict[str, Environment] = {
    "dev": Environment(
        name="dev",
        catalog="rtr_demo_catalog",
        lakebase_project="readmission-worklist",
        lakebase_database="readmission_worklist",
    ),
    "prod": Environment(
        name="prod",
        catalog="prod_care_management",
        lakebase_project="readmission-worklist",
        lakebase_database="readmission_worklist",
    ),
}


class EnvironmentMismatchError(ValueError):
    """Raised when a run's targets do not match its configured environment."""


def assert_environment(
    env: str,
    catalog: str,
    lakebase_project: str | None = None,
    lakebase_database: str | None = None,
) -> Environment:
    """Return the configured Environment, or raise if any supplied target differs."""
    if env not in ENVIRONMENTS:
        raise EnvironmentMismatchError(
            f"Unknown environment '{env}'. Expected one of {sorted(ENVIRONMENTS)}."
        )
    expected = ENVIRONMENTS[env]
    checks = {
        "catalog": (catalog, expected.catalog),
        "lakebase_project": (lakebase_project, expected.lakebase_project),
        "lakebase_database": (lakebase_database, expected.lakebase_database),
    }
    mismatches = [
        f"{field}='{actual}' (expected '{wanted}')"
        for field, (actual, wanted) in checks.items()
        if actual is not None and actual != wanted
    ]
    if mismatches:
        raise EnvironmentMismatchError(
            f"Environment guardrail rejected run for env '{env}': " + "; ".join(mismatches)
        )
    return expected
