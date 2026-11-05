"""Model evaluation: discrimination (AUC), accuracy of probabilities (Brier), and
calibration (slope and intercept of observed outcome on predicted log-odds)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

_EPS = 1e-6


@dataclass(frozen=True)
class EvalMetrics:
    auc: float
    brier: float
    calibration_slope: float
    calibration_intercept: float
    n: int
    observed_rate: float
    mean_predicted: float

    def as_dict(self, prefix: str = "") -> dict[str, float]:
        return {f"{prefix}{k}": float(v) for k, v in asdict(self).items()}


def calibration_slope_intercept(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """Logistic recalibration fit: y ~ a + b * logit(p). Ideal: b = 1, a = 0."""
    p = np.clip(p, _EPS, 1 - _EPS)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    fit = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(logit, y)
    return float(fit.coef_[0][0]), float(fit.intercept_[0])


def evaluate(y, p) -> EvalMetrics:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    slope, intercept = calibration_slope_intercept(y, p)
    return EvalMetrics(
        auc=float(roc_auc_score(y, p)),
        brier=float(brier_score_loss(y, p)),
        calibration_slope=slope,
        calibration_intercept=intercept,
        n=int(len(y)),
        observed_rate=float(y.mean()),
        mean_predicted=float(p.mean()),
    )


def decile_table(y, p) -> list[dict]:
    """Predicted vs. actual readmission rate by risk decile (1 = lowest risk)."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    order = np.argsort(p, kind="stable")
    rows = []
    for i, idx in enumerate(np.array_split(order, 10), start=1):
        rows.append({
            "decile": i,
            "n": int(len(idx)),
            "min_predicted": float(p[idx].min()),
            "max_predicted": float(p[idx].max()),
            "mean_predicted": float(p[idx].mean()),
            "observed_rate": float(y[idx].mean()),
        })
    return rows
