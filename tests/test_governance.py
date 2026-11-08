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
