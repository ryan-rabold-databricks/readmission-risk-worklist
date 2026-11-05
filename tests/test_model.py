import numpy as np
import pandas as pd
import pytest

try:
    import xgboost  # noqa: F401
except Exception as exc:  # XGBoostError when the OpenMP runtime (libomp) is missing
    pytest.skip(f"xgboost unavailable locally: {type(exc).__name__}", allow_module_level=True)

from readmit.ml.drivers import top_drivers
from readmit.ml.features import FEATURE_COLUMNS
from readmit.ml.metrics import evaluate
from readmit.ml.model import contributions, fit, model_frame, predict_proba


def _frame(n, seed):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "age_at_discharge": rng.integers(18, 95, n),
        "length_of_stay_days": rng.integers(1, 15, n),
        "charlson_index": rng.poisson(1.5, n),
        "ed_visits_6m": rng.poisson(0.3, n),
        "inpatient_admits_12m": rng.poisson(0.8, n),
        "emergent_admission": rng.uniform(size=n) < 0.75,
        "followup_scheduled_7d": rng.uniform(size=n) < 0.6,
        "primary_condition_group": rng.choice(["heart_failure", "copd", "other"], n),
        "discharge_disposition": rng.choice(["HOME", "SNF", "AMA", None], n),
    })
    logit = -2.2 + 0.6 * df.inpatient_admits_12m + 0.25 * df.charlson_index + 0.5 * (df.primary_condition_group == "heart_failure")
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-logit))).astype(int)
    return model_frame(df), y


def test_fit_predict_and_drivers_end_to_end():
    X, y = _frame(6000, 1)
    Xv, yv = _frame(1500, 2)
    Xt, yt = _frame(1500, 3)
    pipe = fit(X, y, Xv, yv)
    p = predict_proba(pipe, Xt)
    assert evaluate(yt, p).auc > 0.65
    contrib = contributions(pipe, Xt.head(20))
    assert set(contrib.columns) == set(FEATURE_COLUMNS)
    row = Xt.iloc[0].to_dict()
    drivers = top_drivers(row, contrib.iloc[0].to_dict())
    assert 0 < len(drivers) <= 3 and all(isinstance(d, str) for d in drivers)
    # Contributions plus bias reproduce the model's log-odds.
    logit = np.log(p[:20] / (1 - p[:20]))
    assert np.allclose(contrib.sum(axis=1).values - logit, (contrib.sum(axis=1).values - logit)[0], atol=1e-3)
