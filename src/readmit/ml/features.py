"""Model inputs: columns of readmission_worklist_gold.discharge_features known the
morning after discharge. Outcome columns (followup_within_7d, readmit_30d) are never
inputs (DECISIONS.md #23)."""

from __future__ import annotations

NUMERIC_FEATURES = [
    "age_at_discharge",
    "length_of_stay_days",
    "charlson_index",
    "ed_visits_6m",
    "inpatient_admits_12m",
]
BOOLEAN_FEATURES = ["emergent_admission", "followup_scheduled_7d"]
CATEGORICAL_FEATURES = ["primary_condition_group", "discharge_disposition"]
FEATURE_COLUMNS = NUMERIC_FEATURES + BOOLEAN_FEATURES + CATEGORICAL_FEATURES
LABEL = "readmit_30d"

# Discharges before this date have truncated 6- and 12-month lookbacks (history starts
# 2024-11-01), so they are not used for training.
DEFAULT_TRAIN_START = "2025-11-01"
