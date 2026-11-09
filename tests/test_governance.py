import pytest

from readmit.governance import metric_view as mv


def test_render_fills_every_placeholder():
    sql = mv.create_statement("rtr_demo_catalog", "2026-05-01", "15000")
    assert sql.startswith("CREATE OR REPLACE VIEW rtr_demo_catalog.readmission_worklist_gold.readmission_program_metrics")
    assert "DATE'2026-05-01'" in sql
    assert "MEASURE(readmissions_avoided) * 15000" in sql
    assert "__" not in sql.replace("readmission_worklist_gold", "")  # no placeholder left


@pytest.mark.parametrize("catalog,go_live,cost", [
    ("bad-catalog", "2026-05-01", "15000"),
    ("c; DROP", "2026-05-01", "15000"),
    ("c", "05/01/2026", "15000"),
    ("c", "2026-05-01", "0"),
    ("c", "2026-05-01", "abc"),
])
def test_render_rejects_unsafe_inputs(catalog, go_live, cost):
    with pytest.raises(ValueError):
        mv.render_yaml(catalog, go_live, cost)


from readmit.governance import policies as pol


def test_policies_exempt_only_the_pipeline_identity_on_every_schema():
    stmts = pol.policy_statements("cat", "deployer@example.org")
    assert len(stmts) == 3 * len(pol.POLICY_SCHEMAS)
    assert all("TO `account users` EXCEPT `deployer@example.org`" in s for s in stmts)
    assert {s.split(" ON SCHEMA ")[1].split()[0] for s in stmts} == {f"cat.{s}" for s in pol.POLICY_SCHEMAS}


def test_policy_rejects_backtick_principal():
    with pytest.raises(ValueError):
        pol.policy_statements("cat", "x` TO `y")


def test_every_tagged_value_is_masked_and_facility_tables_are_tagged():
    tags = pol.column_tags("cat")
    phi_values = {t.tag_value for t in tags if t.tag_key == pol.PHI_TAG}
    assert phi_values <= set(pol.DIRECT_CATEGORIES) | {"date"}
    assert {t.entity_name for t in tags if t.tag_key == pol.SCOPE_TAG} == {
        f"cat.{s}.{t}.facility_id" for s, t in pol.FACILITY_TABLES}
    # The filter function reads care_team_assignment, so that table must not be filtered.
    assert ("care_management_silver", "care_team_assignment") not in pol.FACILITY_TABLES


class _P:
    def __init__(self, name, on, conds, when=None):
        self.name, self.on_securable_fullname, self.when_condition = name, on, when
        self.match_columns = [type("M", (), {"condition": c})() for c in conds]


def test_conflicts_flag_foreign_policies_on_our_tags_only():
    found = {"clinical_silver": [
        _P("readmit_mask_direct_identifier", "cat.clinical_silver", ["has_tag_value('phi_data_classification', 'name')"]),
        _P("classification_row_filter", "cat", ["hasTagValue('row_filter_policy', 'attr_id')"]),
        _P("other_facility_rls", "cat", ["has_tag_value('row_filter_policy', 'facility_id')"]),
        _P("readmit_spoof", "cat", ["has_tag_value('phi_data_classification', 'mrn')"]),
    ]}
    assert pol.conflicting_policies(found) == ["other_facility_rls on cat", "readmit_spoof on cat"]
