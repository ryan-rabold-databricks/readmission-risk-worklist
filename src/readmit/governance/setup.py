"""<env>_readmit_governance: idempotent PHI governance and semantic layer setup.

Runs after the pipeline (it needs the silver and gold tables). Every step is safe to
rerun: tags are set to their declared values, functions, policies, and the metric view
are CREATE OR REPLACE.

1. Fail if foreign class.* tags sit on project columns (DECISIONS.md #60).
2. Fail if another project's policy matches the tags used here; set column tags.
3. Mask and row filter functions in phi_governance; schema-level ABAC policies that
   exempt only the pipeline's run-as identity.
4. Metric view readmission_worklist_gold.readmission_program_metrics.

SQL runs on the SQL warehouse: creating policies that use tag functions needs
Databricks Runtime 18 or above (ABAC docs).
"""

from __future__ import annotations

import argparse
import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.catalog import EntityTagAssignment
from databricks.sdk.service.sql import StatementState

from readmit.common.env_guardrail import assert_environment
from readmit.governance import metric_view, policies


def run_sql(w: WorkspaceClient, warehouse_id: str, sql: str) -> list[list[str]]:
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=warehouse_id, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"{r.status.state}: {r.status.error.message if r.status.error else ''}\n{sql[:400]}")
    return (r.result.data_array or []) if r.result else []


def check_governed_tags(w: WorkspaceClient) -> None:
    """Both tags are existing account-level governed tags this project does not create."""
    need = {policies.PHI_TAG: {*policies.DIRECT_CATEGORIES, "date"}, policies.SCOPE_TAG: {policies.SCOPE_VALUE}}
    for key, values in need.items():
        have = {v.name for v in (w.tag_policies.get_tag_policy(key).values or [])}
        if missing := values - have:
            raise RuntimeError(f"Governed tag {key} lacks values {sorted(missing)}")


def check_policy_conflicts(w: WorkspaceClient, catalog: str) -> None:
    found = {s: list(w.policies.list_policies("SCHEMA", f"{catalog}.{s}", include_inherited=True))
             for s in policies.POLICY_SCHEMAS}
    if conflicts := policies.conflicting_policies(found):
        raise RuntimeError(f"Policies from other projects match {policies.PHI_TAG} or "
                           f"{policies.SCOPE_TAG}={policies.SCOPE_VALUE}: {conflicts}")


def apply_column_tags(w: WorkspaceClient, catalog: str) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for t in policies.column_tags(catalog):
        want = EntityTagAssignment(entity_type="columns", entity_name=t.entity_name, tag_key=t.tag_key, tag_value=t.tag_value)
        try:
            have = w.entity_tag_assignments.get("columns", t.entity_name, t.tag_key)
        except NotFound:
            w.entity_tag_assignments.create(want)
            counts["created"] += 1
            continue
        if have.tag_value == t.tag_value:
            counts["unchanged"] += 1
        else:
            w.entity_tag_assignments.update("columns", t.entity_name, t.tag_key, want, update_mask="tag_value")
            counts["updated"] += 1
    return counts


def pipeline_identity(w: WorkspaceClient, pipeline_id: str) -> str:
    p = w.pipelines.get(pipeline_id)
    identity = p.run_as_user_name or p.creator_user_name
    if not identity:
        raise RuntimeError(f"Pipeline {pipeline_id} has no run-as identity")
    me = w.current_user.me().user_name
    if identity != me:
        # Jobs and synced tables run as the deploying identity too; a mismatch means one
        # of them would be masked and write masked data.
        raise RuntimeError(f"Governance job runs as {me} but the pipeline runs as {identity}")
    return identity


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--warehouse-id", required=True)
    p.add_argument("--pipeline-id", required=True)
    p.add_argument("--leadership-group", required=True)
    p.add_argument("--go-live", required=True)
    p.add_argument("--avg-cost", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    assert_environment(args.env, args.catalog)
    w = WorkspaceClient()
    sql = lambda s: run_sql(w, args.warehouse_id, s)  # noqa: E731

    foreign = sql(policies.foreign_tag_query(args.catalog))
    if foreign:
        raise RuntimeError(
            "class.* tags on project columns would be masked by catalog-level policies from other "
            f"projects and conflict with readmit masks; remove them and exclude these schemas from "
            f"auto-tagging (DECISIONS.md #60): {foreign}")

    check_governed_tags(w)
    check_policy_conflicts(w, args.catalog)
    exempt = pipeline_identity(w, args.pipeline_id)
    summary = {"exempt_principal": exempt, "column_tags": apply_column_tags(w, args.catalog)}
    for s in policies.function_statements(args.catalog, args.leadership_group):
        sql(s)
    summary["functions"] = 3
    for s in policies.policy_statements(args.catalog, exempt):
        sql(s)
    summary["policies"] = len(policies.POLICY_SCHEMAS) * 3
    sql(metric_view.create_statement(args.catalog, args.go_live, args.avg_cost))
    summary["metric_view"] = f"{args.catalog}.{metric_view.METRIC_VIEW}"
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
