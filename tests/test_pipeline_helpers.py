from pathlib import Path

from readmit.common.clinical_codes import CHARLSON_CATEGORIES, CONDITION_GROUP_PREFIXES
from readmit.pipeline.clinical_exprs import CHARLSON_HIERARCHY, prefixes_longest_first
from readmit.pipeline.quality_rules import RULES
from readmit.pipeline.seeds import SEED_SCHEMAS, read_seed_rows
from readmit.pipeline.source_schemas import SOURCE_SCHEMAS

SEEDS = Path(__file__).resolve().parents[1] / "seeds"


def test_longest_prefix_wins():
    ordered = prefixes_longest_first(CONDITION_GROUP_PREFIXES)
    assert ordered.index("I11.0") < ordered.index("I50")
    assert all(len(a) >= len(b) for a, b in zip(ordered, ordered[1:]))


def test_charlson_hierarchy_names_exist():
    for severe, mild in CHARLSON_HIERARCHY.items():
        assert severe in CHARLSON_CATEGORIES and mild in CHARLSON_CATEGORIES


def test_every_source_entity_has_rules_and_schema():
    assert set(RULES) == set(SOURCE_SCHEMAS) == {"patient", "encounter", "diagnosis", "appointment"}
    for rules in RULES.values():
        assert "schema_conforms" in rules and "record_timestamps_present" in rules


def test_seed_files_match_seed_schemas():
    for name, ddl in SEED_SCHEMAS.items():
        columns = [f.strip().split(" ", 1)[0] for f in ddl.split(",")]
        rows = read_seed_rows(str(SEEDS), name)
        assert rows, name
        assert list(rows[0].keys()) == columns, name


def test_risk_tiers_cover_zero_to_one_without_gaps():
    tiers = sorted(read_seed_rows(str(SEEDS), "risk_tier_policy"), key=lambda r: float(r["min_score"]))
    assert float(tiers[0]["min_score"]) == 0.0 and float(tiers[-1]["max_score"]) == 1.0
    for low, high in zip(tiers, tiers[1:]):
        assert low["max_score"] == high["min_score"]
