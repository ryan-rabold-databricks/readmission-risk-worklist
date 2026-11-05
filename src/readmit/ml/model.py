"""Model definition: one-hot encoding + XGBoost in a plain scikit-learn Pipeline, so the
registered model loads without this package."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import DMatrix, XGBClassifier

from readmit.ml.drivers import source_feature
from readmit.ml.features import BOOLEAN_FEATURES, CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES

XGB_PARAMS = {
    "n_estimators": 800,
    "learning_rate": 0.04,
    "max_depth": 4,
    "min_child_weight": 10,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 2.0,
    "eval_metric": "logloss",
    "early_stopping_rounds": 50,
    "random_state": 42,
    "n_jobs": 4,
}


def model_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Typed model input: numerics as float, booleans as bool, categoricals as str."""
    out = pd.DataFrame(index=df.index)
    for c in NUMERIC_FEATURES:
        out[c] = df[c].astype("float64")
    for c in BOOLEAN_FEATURES:
        out[c] = df[c].astype(bool)
    for c in CATEGORICAL_FEATURES:
        out[c] = df[c].fillna("UNKNOWN").astype(str)
    return out[FEATURE_COLUMNS]


def _preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("num", "passthrough", NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), BOOLEAN_FEATURES + CATEGORICAL_FEATURES),
        ]
    )


def fit(X_train: pd.DataFrame, y_train, X_val: pd.DataFrame, y_val) -> Pipeline:
    """Fit with early stopping on a later validation window; return the fitted Pipeline."""
    pre = _preprocessor().fit(X_train)
    clf = XGBClassifier(**XGB_PARAMS)
    clf.fit(pre.transform(X_train), y_train, eval_set=[(pre.transform(X_val), y_val)], verbose=False)
    return Pipeline([("pre", pre), ("clf", clf)])


def predict_proba(pipeline: Pipeline, X: pd.DataFrame) -> np.ndarray:
    return pipeline.predict_proba(X)[:, 1]


def contributions(pipeline: Pipeline, X: pd.DataFrame) -> pd.DataFrame:
    """Per-row TreeSHAP contributions (log-odds), summed back to source features."""
    pre, clf = pipeline.named_steps["pre"], pipeline.named_steps["clf"]
    names = list(pre.get_feature_names_out())
    booster = clf.get_booster()
    best = getattr(clf, "best_iteration", None)
    kwargs = {"iteration_range": (0, best + 1)} if best is not None else {}
    raw = booster.predict(DMatrix(pre.transform(X)), pred_contribs=True, **kwargs)
    by_name = pd.DataFrame(raw[:, :-1], columns=names, index=X.index)  # last column is the bias
    return by_name.T.groupby([source_feature(n) for n in names]).sum().T
