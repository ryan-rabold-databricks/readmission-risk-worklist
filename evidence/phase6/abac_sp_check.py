"""ABAC validation as a non-exempt test service principal (DECISIONS.md #62).

Run by the author (the auto-mode agent may not mint credentials):
    .venv/bin/python -I evidence/phase6/abac_sp_check.py | tee evidence/phase6/abac_validation_sp_<n>.raw.txt

Creates (once) service principal readmit-phi-test with workspace and SQL access and
CAN_USE on the dev warehouse. A one-hour OAuth secret exists only inside this process and
is deleted at the end. The leadership path adds the SP to care_mgmt_leadership for the
duration of the check and removes it afterward. Output carries masked values only.
"""
import json
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import iam
from databricks.sdk.service.sql import StatementState

PROFILE, WH, CAT, NAME = "fevm-classic-stable", "b2f6ee775c2fa42c", "rtr_demo_catalog", "readmit-phi-test"
LEADERSHIP = "care_mgmt_leadership"
GOLD = f"{CAT}.readmission_worklist_gold"

CHECKS = {
    "identity": f"SELECT current_user() AS me, is_member('{LEADERSHIP}') AS leader, is_account_group_member('{LEADERSHIP}') AS account_leader",
    "silver_patient": f"SELECT first_name, last_name, mrn, phone, zip_code, birth_date FROM {CAT}.clinical_silver.patient ORDER BY patient_id LIMIT 2",
    "bronze_patient": f"SELECT first_name, mrn, phone, birth_date FROM {CAT}.ehr_bronze.patient_raw LIMIT 1",
    "bronze_encounter": f"SELECT count(*) AS n, max(encounter_number) AS sample FROM {CAT}.ehr_bronze.encounter_raw",
    "silver_encounter": f"SELECT count(*) AS n, max(encounter_number) AS sample FROM {CAT}.clinical_silver.encounter",
    "care_worklist": f"SELECT count(*) AS n, max(patient_display_name) AS name, max(phone) AS phone FROM {GOLD}.care_worklist",
    "care_worklist_active_view": f"SELECT count(*) AS n, max(patient_display_name) AS name FROM {GOLD}.care_worklist_active",
    "readmission_outcome": f"SELECT count(*) AS n, count(DISTINCT facility_id) AS facilities FROM {GOLD}.readmission_outcome",
    "metric_view": f"SELECT MEASURE(program_discharges) AS program_discharges, MEASURE(est_cost_avoided) AS cost FROM {GOLD}.readmission_program_metrics",
    "synced_foreign_table": f"SELECT count(*) AS n, max(patient_display_name) AS name FROM {GOLD}.care_worklist_synced",
    "hidden_materialization": f"SELECT first_name FROM {CAT}.clinical_silver.__materialization_mat_681e67de_8388_473c_95d2_56d9e3aa606f_patient_1 LIMIT 1",
    "app_bronze_outreach": f"SELECT count(*) AS n FROM {CAT}.readmission_worklist_app_bronze.lb_outreach_activity_history",
}
LEADER_CHECKS = ["identity", "silver_patient", "readmission_outcome", "metric_view", "care_worklist", "synced_foreign_table"]


def q(w: WorkspaceClient, sql: str):
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=WH, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        return f"ERROR: {r.status.error.message.splitlines()[0][:200]}"
    cols = [c.name for c in r.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in (r.result.data_array or [])]


def scim(op: iam.Patch) -> dict:
    return {"operations": [op], "schemas": [iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP]}


def main() -> None:
    admin = WorkspaceClient(profile=PROFILE)
    sp = next(iter(admin.service_principals.list(filter=f'displayName eq "{NAME}"')), None)
    if sp is None:
        sp = admin.service_principals.create(display_name=NAME, active=True, entitlements=[
            iam.ComplexValue(value="workspace-access"), iam.ComplexValue(value="databricks-sql-access")])
    admin.permissions.update("warehouses", WH, access_control_list=[iam.AccessControlRequest(
        service_principal_name=sp.application_id, permission_level=iam.PermissionLevel.CAN_USE)])
    group = next(iter(admin.groups.list(filter=f'displayName eq "{LEADERSHIP}"')))
    out = {"test_sp": sp.application_id}
    secret = admin.service_principal_secrets_proxy.create(sp.id, lifetime="3600s")
    try:
        time.sleep(5)
        w = WorkspaceClient(host=admin.config.host, client_id=sp.application_id,
                            client_secret=secret.secret, auth_type="oauth-m2m")
        out["not_leader"] = {k: q(w, v) for k, v in CHECKS.items()}
        admin.groups.patch(group.id, **scim(iam.Patch(op=iam.PatchOp.ADD, value={"members": [{"value": sp.id}]})))
        try:
            # Poll until the filter's is_member() sees the membership (DECISIONS.md #65), up to 10 min.
            start = time.time()
            while time.time() - start < 600:
                time.sleep(30)
                ident = q(w, CHECKS["identity"])
                if isinstance(ident, list) and ident and ident[0]["leader"] == "true":
                    break
            out["leader_wait_seconds"] = round(time.time() - start)
            out["leader"] = {k: q(w, CHECKS[k]) for k in LEADER_CHECKS}
        finally:
            admin.groups.patch(group.id, **scim(iam.Patch(op=iam.PatchOp.REMOVE, path=f'members[value eq "{sp.id}"]')))
    finally:
        admin.service_principal_secrets_proxy.delete(sp.id, secret.id)
    out["cleanup"] = "secret deleted; SP removed from leadership group"
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
