import numpy as np
import pytest

from readmit.ml.drivers import describe, source_feature, top_drivers
from readmit.ml.features import FEATURE_COLUMNS
from readmit.ml.gates import Gates, decide
from readmit.ml.metrics import EvalMetrics, calibration_slope_intercept, decile_table, evaluate
from readmit.worklist.assign import ASSIGNED, OVERFLOW, assign_items


def _m(auc, brier, slope=1.0):
    return EvalMetrics(auc, brier, slope, 0.0, 1000, 0.15, 0.15)


def test_perfectly_calibrated_predictions_have_slope_near_one():
    rng = np.random.default_rng(7)
    p = rng.uniform(0.02, 0.6, 50_000)
    y = rng.uniform(size=p.size) < p
    slope, intercept = calibration_slope_intercept(y.astype(int), p)
    assert slope == pytest.approx(1.0, abs=0.05)
    assert intercept == pytest.approx(0.0, abs=0.08)


def test_overconfident_predictions_have_slope_below_one():
    rng = np.random.default_rng(7)
    p = rng.uniform(0.05, 0.5, 50_000)
    y = rng.uniform(size=p.size) < p
    logit = np.log(p / (1 - p))
    extreme = 1 / (1 + np.exp(-(2 * logit)))
    slope, _ = calibration_slope_intercept(y.astype(int), extreme)
    assert slope < 0.8


def test_decile_table_has_ten_ordered_bins():
    rng = np.random.default_rng(1)
    p = rng.uniform(size=1000)
    y = (rng.uniform(size=1000) < p).astype(int)
    table = decile_table(y, p)
    assert [r["decile"] for r in table] == list(range(1, 11))
    assert sum(r["n"] for r in table) == 1000
    assert table[0]["mean_predicted"] < table[-1]["mean_predicted"]
    assert evaluate(y, p).n == 1000


def test_first_model_gates():
    g = Gates()
    assert decide(_m(0.70, 0.12, 1.05), None, g).promote
    assert not decide(_m(0.67, 0.12, 1.0), None, g).promote
    assert not decide(_m(0.75, 0.12, 0.7), None, g).promote


def test_challenger_gates():
    g = Gates()
    champion = _m(0.72, 0.120)
    assert decide(_m(0.716, 0.119), champion, g).promote
    assert not decide(_m(0.714, 0.119), champion, g).promote
    assert not decide(_m(0.73, 0.121), champion, g).promote


def test_driver_text_and_feature_mapping():
    assert describe("inpatient_admits_12m", 1) == "1 inpatient stay in the prior 12 months"
    assert describe("followup_scheduled_7d", False) == "No follow-up booked within 7 days"
    assert source_feature("cat__discharge_disposition_SNF") == "discharge_disposition"
    assert source_feature("num__charlson_index") == "charlson_index"
    for col in FEATURE_COLUMNS:
        assert source_feature(f"x__{col}") == col or col in ("primary_condition_group", "discharge_disposition")


def test_top_drivers_only_risk_increasing():
    row = {"inpatient_admits_12m": 3, "charlson_index": 4, "age_at_discharge": 70, "length_of_stay_days": 2}
    contribs = {"inpatient_admits_12m": 0.5, "charlson_index": 0.2, "age_at_discharge": -0.1, "length_of_stay_days": 0.0}
    assert top_drivers(row, contribs) == [
        "3 inpatient stays in the prior 12 months",
        "Comorbidity burden (Charlson index 4)",
    ]


def test_assignment_caps_capacity_highest_risk_first():
    roster = [
        {"care_manager_email": "a@x", "facility_id": "F1", "daily_capacity": 2},
        {"care_manager_email": "a@x", "facility_id": "F2", "daily_capacity": 2},
        {"care_manager_email": "b@x", "facility_id": "F2", "daily_capacity": 1},
    ]
    items = [
        {"worklist_item_id": "i1", "facility_id": "F1", "risk_score": 0.9},
        {"worklist_item_id": "i2", "facility_id": "F2", "risk_score": 0.8},
        {"worklist_item_id": "i3", "facility_id": "F1", "risk_score": 0.7},
        {"worklist_item_id": "i4", "facility_id": "F2", "risk_score": 0.6},
        {"worklist_item_id": "i5", "facility_id": "F3", "risk_score": 0.95},
    ]
    got = {a.worklist_item_id: (a.care_manager_email, a.status) for a in assign_items(items, roster)}
    assert got == {
        "i5": (None, OVERFLOW),       # nobody rostered at F3
        "i1": ("a@x", ASSIGNED),
        "i2": ("a@x", ASSIGNED),      # a and b both have 1 left; tie breaks by email
        "i3": (None, OVERFLOW),       # a is at capacity and is the only one at F1
        "i4": ("b@x", ASSIGNED),
    }


def test_assignment_is_deterministic_and_respects_capacity():
    roster = [{"care_manager_email": "a@x", "facility_id": "F1", "daily_capacity": 3}]
    items = [{"worklist_item_id": f"i{n}", "facility_id": "F1", "risk_score": 0.5} for n in range(5)]
    first = assign_items(items, roster)
    assert first == assign_items(list(reversed(items)), roster)
    assert [a.status for a in first].count(ASSIGNED) == 3


def test_backfill_month_starts():
    from datetime import date

    from readmit.common.dates import month_starts

    assert month_starts(date(2026, 5, 1), date(2026, 7, 3)) == [date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1)]
    assert month_starts(date(2026, 5, 15), date(2026, 6, 2)) == [date(2026, 5, 15), date(2026, 6, 1)]
    assert month_starts(date(2026, 12, 1), date(2027, 1, 5)) == [date(2026, 12, 1), date(2027, 1, 1)]


def test_tier_for_boundaries():
    import pandas as pd

    from readmit.ml.tiers import tier_for

    policy = pd.DataFrame({"risk_tier": ["LOW", "MEDIUM", "HIGH"], "min_score": [0.0, 0.18, 0.30], "max_score": [0.18, 0.30, 1.0]})
    assert tier_for(0.0, policy) == "LOW"
    assert tier_for(0.18, policy) == "MEDIUM"
    assert tier_for(0.2999, policy) == "MEDIUM"
    assert tier_for(0.30, policy) == "HIGH"
    assert tier_for(1.0, policy) == "HIGH"
