import csv
from datetime import date
from pathlib import Path

import pytest

from readmit.common.clinical_codes import (
    CHARLSON_CATEGORIES,
    CONDITION_PRIMARY_CODES,
    DRG_BY_CONDITION,
    condition_group_for,
)
from readmit.simulator.config import (
    CONDITION_MIX,
    EMERGENT_RATE,
    FACILITIES,
    MEDIAN_LOS_DAYS,
    COMORBIDITY_LOGIT,
    SimulatorConfig,
)
from readmit.simulator.main import missing_dates, resolve_run_date

SEEDS = Path(__file__).resolve().parents[1] / "seeds"


def test_facility_profiles_match_seed_file():
    with open(SEEDS / "facility.csv") as fh:
        seeded = {row["facility_id"] for row in csv.DictReader(fh)}
    assert {f.facility_id for f in FACILITIES} == seeded


def test_facility_volume_shares_sum_to_one():
    assert sum(f.volume_share for f in FACILITIES) == pytest.approx(1.0)


def test_every_condition_has_codes_and_parameters():
    conditions = set(CONDITION_MIX)
    for table in (CONDITION_PRIMARY_CODES, EMERGENT_RATE, MEDIAN_LOS_DAYS, DRG_BY_CONDITION):
        assert set(table) == conditions


def test_comorbidity_parameters_cover_every_charlson_category():
    assert set(COMORBIDITY_LOGIT) == set(CHARLSON_CATEGORIES)


@pytest.mark.parametrize(
    "condition,codes", [(c, v) for c, v in CONDITION_PRIMARY_CODES.items() if c != "other"]
)
def test_primary_codes_map_back_to_their_condition(condition, codes):
    assert all(condition_group_for(code) == condition for code in codes)


def test_unmapped_code_returns_none():
    assert condition_group_for("Z99.9") is None


def test_run_date_defaults_to_yesterday():
    assert resolve_run_date("", date(2026, 11, 2)) == date(2026, 11, 1)


def test_run_date_today_or_later_is_rejected():
    with pytest.raises(ValueError):
        resolve_run_date("2026-11-02", date(2026, 11, 2))


def test_missing_dates_skips_landed_and_fills_gaps():
    landed = {date(2026, 1, 1), date(2026, 1, 3)}
    assert missing_dates(date(2026, 1, 1), date(2026, 1, 4), landed) == [date(2026, 1, 2), date(2026, 1, 4)]


def test_config_rejects_run_date_before_history():
    with pytest.raises(ValueError):
        SimulatorConfig(history_start=date(2026, 1, 2), run_date=date(2026, 1, 1))


def test_generator_version_guard_rejects_mixed_versions():
    from readmit.simulator.landing import assert_single_generator_version, landed_dates

    manifests = [{"generator_version": "1", "extract_dates": ["2026-01-01"]}]
    assert landed_dates(manifests) == {date(2026, 1, 1)}
    assert_single_generator_version([], "2")
    assert_single_generator_version([{"generator_version": "2", "extract_dates": []}], "2")
    with pytest.raises(RuntimeError, match="generator version"):
        assert_single_generator_version(manifests, "2")
