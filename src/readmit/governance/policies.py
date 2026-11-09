"""PHI tags, mask and row filter functions, and ABAC policies (DECISIONS.md #60, #62).

Columns carry the account-level governed tag phi_data_classification (HIPAA Safe Harbor
categories) and facility_id columns carry row_filter_policy = facility_id (an existing
governed tag reused because the account is at its tag policy limit). Schema-level
ABAC policies on every schema that holds patient-level data then mask and filter any
tagged column, including in tables added later. The pipeline identity (the run-as user
of the pipeline, which also owns the jobs and synced tables) is the only exemption:
if it were masked, refreshes would write masked values permanently (ABAC docs).
"""

from __future__ import annotations

from dataclasses import dataclass

PHI_TAG = "phi_data_classification"
SCOPE_TAG = "row_filter_policy"
SCOPE_VALUE = "facility_id"
GOVERNANCE_SCHEMA = "phi_governance"

# Categories masked to '***'; 'date' (birth date) is masked to the year instead.
DIRECT_CATEGORIES = ("name", "mrn", "phone_number", "address", "account_number")

_PATIENT = {"first_name": "name", "last_name": "name", "mrn": "mrn", "phone": "phone_number",
            "zip_code": "address", "birth_date": "date"}
PHI_COLUMNS: dict[tuple[str, str], dict[str, str]] = {
    ("ehr_bronze", "patient_raw"): _PATIENT,
    ("ehr_bronze", "encounter_raw"): {"mrn": "mrn", "encounter_number": "account_number"},
    ("ehr_bronze", "diagnosis_raw"): {"encounter_number": "account_number"},
    ("ehr_bronze", "appointment_raw"): {"mrn": "mrn", "source_encounter_number": "account_number"},
    ("clinical_silver", "patient"): _PATIENT,
    ("clinical_silver", "encounter"): {"encounter_number": "account_number"},
    ("readmission_worklist_gold", "care_worklist"): {"patient_display_name": "name", "phone": "phone_number"},
    # UC foreign table over the Lakebase copy; account users inherit catalog SELECT on it
    # (DECISIONS.md #66). The app reads Postgres directly, so this does not affect it.
    ("readmission_worklist_gold", "care_worklist_synced"): {"patient_display_name": "name", "phone": "phone_number"},
}
# Patient-level facts filtered to the reader's facilities. Reference and roster tables
# (facility, care_team_assignment, care_team_roster) are not filtered: the filter
# function itself reads care_team_assignment.
FACILITY_TABLES = (
    ("ehr_bronze", "encounter_raw"),
    ("clinical_silver", "encounter"),
    ("readmission_worklist_gold", "discharge_features"),
    ("readmission_worklist_gold", "readmission_outcome"),
    ("readmission_worklist_gold", "care_worklist"),
    ("readmission_worklist_gold", "care_worklist_synced"),
)
POLICY_SCHEMAS = ("ehr_bronze", "clinical_silver", "care_management_silver", "readmission_worklist_gold")
POLICY_PREFIX = "readmit_"
# What leadership reads as itself: the app's Program and Program Settings queries
# (*.obo.sql) and the Genie Agent's tables (DECISIONS.md #54, #63, #65).
LEADER_READ = {
    "clinical_silver": ("facility",),
    "care_management_silver": ("care_manager_capacity", "care_team_assignment", "program_setting", "risk_tier_policy"),
    "readmission_worklist_gold": ("readmission_outcome", "readmission_program_metrics", "care_worklist"),
}


def conflicting_policies(policies_by_schema: dict[str, list]) -> list[str]:
    """Policies not owned by this project whose conditions match the tags we rely on.

    Only one row filter and one mask per column may resolve for a user, so another
    project's policy matching these tags would make queries fail.
    """
    markers = (f"'{PHI_TAG}'", f"'{SCOPE_VALUE}'")
    out = set()
    for schema, infos in policies_by_schema.items():
        for p in infos:
            if p.name.startswith(POLICY_PREFIX) and str(p.on_securable_fullname).endswith(f".{schema}"):
                continue
            conds = [m.condition for m in (p.match_columns or [])] + [p.when_condition or ""]
            if any(mk in c for c in conds for mk in markers):
                out.add(f"{p.name} on {p.on_securable_fullname}")
    return sorted(out)


@dataclass(frozen=True)
class ColumnTag:
    entity_name: str  # catalog.schema.table.column
    tag_key: str
    tag_value: str


def column_tags(catalog: str) -> list[ColumnTag]:
    out = [ColumnTag(f"{catalog}.{s}.{t}.{c}", PHI_TAG, v)
           for (s, t), cols in PHI_COLUMNS.items() for c, v in cols.items()]
    out += [ColumnTag(f"{catalog}.{s}.{t}.facility_id", SCOPE_TAG, SCOPE_VALUE) for s, t in FACILITY_TABLES]
    return out


def _q(principal: str) -> str:
    if "`" in principal:
        raise ValueError(f"Invalid principal name: {principal!r}")
    return f"`{principal}`"


def function_statements(catalog: str, leadership_group: str) -> list[str]:
    fq = f"{catalog}.{GOVERNANCE_SCHEMA}"
    group = leadership_group.replace("'", "")
    return [
        f"""CREATE OR REPLACE FUNCTION {fq}.mask_direct_identifier(value STRING)
RETURNS STRING
COMMENT 'ABAC column mask for direct identifiers (phi_data_classification name, mrn, phone_number, address, account_number).'
RETURN CASE WHEN value IS NULL THEN NULL ELSE '***' END""",
        # Safe Harbor keeps the year, except for ages over 89.
        f"""CREATE OR REPLACE FUNCTION {fq}.mask_birth_date(value DATE)
RETURNS DATE
COMMENT 'ABAC column mask for birth dates: January 1 of the birth year; NULL when the patient would be over 89.'
RETURN CASE WHEN value IS NULL OR year(value) <= year(current_date()) - 90 THEN NULL
            ELSE make_date(year(value), 1, 1) END""",
        f"""CREATE OR REPLACE FUNCTION {fq}.filter_by_facility(facility_id STRING)
RETURNS BOOLEAN
COMMENT 'ABAC row filter: {group} sees every facility; anyone else sees the facilities they are assigned to today in care_team_assignment.'
RETURN is_member('{group}') OR EXISTS (
  SELECT 1 FROM {catalog}.care_management_silver.care_team_assignment a
  WHERE a.facility_id = filter_by_facility.facility_id
    AND a.care_manager_email = lower(current_user())
    AND a.effective_date <= current_date()
    AND (a.expiration_date IS NULL OR a.expiration_date > current_date()))""",
    ]


def grant_statements(catalog: str, leadership_group: str, masked_reader_group: str = "",
                     leader_grants: bool = True) -> list[str]:
    """Schema and table grants; GRANT is additive and idempotent. USE CATALOG is the
    catalog owner's to grant and is not issued here.

    masked_reader_group (dev: `account users`, which already holds catalog-wide SELECT,
    DECISIONS.md #6) gets USE SCHEMA on every masked schema, so it reads through the masks.
    leader_grants is False for a workspace-local leadership group, which Unity Catalog
    cannot grant to (DECISIONS.md #65).
    """
    lead = _q(leadership_group)
    out = []
    if leader_grants:
        out += [f"GRANT USE SCHEMA ON SCHEMA {catalog}.{s} TO {lead}" for s in LEADER_READ]
        out += [f"GRANT SELECT ON TABLE {catalog}.{s}.{t} TO {lead}" for s, ts in LEADER_READ.items() for t in ts]
    if masked_reader_group:
        out += [f"GRANT USE SCHEMA ON SCHEMA {catalog}.{s} TO {_q(masked_reader_group)}" for s in POLICY_SCHEMAS]
    return out


def policy_statements(catalog: str, exempt_principal: str) -> list[str]:
    fq = f"{catalog}.{GOVERNANCE_SCHEMA}"
    to = f"TO `account users` EXCEPT {_q(exempt_principal)}"
    direct = " OR ".join(f"has_tag_value('{PHI_TAG}', '{c}')" for c in DIRECT_CATEGORIES)
    stmts = []
    for schema in POLICY_SCHEMAS:
        on = f"ON SCHEMA {catalog}.{schema}"
        stmts += [
            f"""CREATE OR REPLACE POLICY readmit_mask_direct_identifier {on}
COMMENT 'Mask direct identifiers for everyone but the pipeline identity.'
COLUMN MASK {fq}.mask_direct_identifier {to}
FOR TABLES MATCH COLUMNS {direct} AS c ON COLUMN c""",
            f"""CREATE OR REPLACE POLICY readmit_mask_birth_date {on}
COMMENT 'Reduce birth dates to the year for everyone but the pipeline identity.'
COLUMN MASK {fq}.mask_birth_date {to}
FOR TABLES MATCH COLUMNS has_tag_value('{PHI_TAG}', 'date') AS c ON COLUMN c""",
            f"""CREATE OR REPLACE POLICY readmit_filter_by_facility {on}
COMMENT 'Limit patient-level rows to the reader''s facilities (leadership sees all).'
ROW FILTER {fq}.filter_by_facility {to}
FOR TABLES MATCH COLUMNS has_tag_value('{SCOPE_TAG}', '{SCOPE_VALUE}') AS f USING COLUMNS (f)""",
        ]
    return stmts


# Catalog-level policies from other demos in a shared dev catalog mask class.name and
# class.location; only one mask may resolve per column, and a masked pipeline identity
# writes masked data (DECISIONS.md #60).
def foreign_tag_query(catalog: str) -> str:
    schemas = ", ".join(f"'{s}'" for s in POLICY_SCHEMAS)
    return (f"SELECT concat_ws('.', schema_name, table_name, column_name) AS col, tag_name "
            f"FROM {catalog}.information_schema.column_tags "
            f"WHERE schema_name IN ({schemas}) AND tag_name LIKE 'class.%' AND table_name NOT LIKE '\\\\_\\\\_%'")
