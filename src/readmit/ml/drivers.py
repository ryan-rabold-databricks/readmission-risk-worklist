"""Top risk drivers in plain language, from per-feature model contributions.

Contributions come from XGBoost's own TreeSHAP (pred_contribs); one-hot columns are
summed back to their source feature. Only risk-increasing drivers are listed.
"""

from __future__ import annotations

from readmit.ml.features import BOOLEAN_FEATURES, CATEGORICAL_FEATURES, FEATURE_COLUMNS

CONDITION_LABELS = {
    "heart_failure": "Heart failure admission",
    "copd": "COPD admission",
    "pneumonia": "Pneumonia admission",
    "ami": "Heart attack (AMI) admission",
    "sepsis": "Sepsis admission",
    "diabetes": "Diabetes admission",
    "ortho_surgery": "Orthopedic surgery admission",
    "gi": "GI admission",
    "other": "Admission diagnosis",
}
DISPOSITION_LABELS = {
    "HOME": "Discharged home without services",
    "HOME_HEALTH": "Discharged home with home health",
    "SNF": "Discharged to a skilled nursing facility",
    "REHAB": "Discharged to rehab",
    "AMA": "Left against medical advice",
}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def describe(feature: str, value) -> str:
    if feature == "inpatient_admits_12m":
        return f"{_plural(int(value), 'inpatient stay')} in the prior 12 months"
    if feature == "ed_visits_6m":
        return f"{_plural(int(value), 'ED visit')} in the prior 6 months"
    if feature == "charlson_index":
        return f"Comorbidity burden (Charlson index {int(value)})"
    if feature == "length_of_stay_days":
        return f"{int(value)}-day hospital stay"
    if feature == "age_at_discharge":
        return f"Age {int(value)}"
    if feature == "emergent_admission":
        return "Emergency admission" if bool(value) else "Elective admission"
    if feature == "followup_scheduled_7d":
        return "Follow-up booked within 7 days" if bool(value) else "No follow-up booked within 7 days"
    if feature == "primary_condition_group":
        return CONDITION_LABELS.get(str(value), "Admission diagnosis")
    if feature == "discharge_disposition":
        return DISPOSITION_LABELS.get(str(value), f"Discharge disposition {value}")
    raise KeyError(feature)


def source_feature(transformed_name: str) -> str:
    """Map a ColumnTransformer output name (e.g. 'cat__discharge_disposition_SNF')."""
    name = transformed_name.split("__", 1)[-1]
    for col in CATEGORICAL_FEATURES + BOOLEAN_FEATURES:
        if name.startswith(col + "_"):
            return col
    if name in FEATURE_COLUMNS:
        return name
    raise KeyError(transformed_name)


def top_drivers(row: dict, contributions: dict[str, float], k: int = 3) -> list[str]:
    positive = sorted(
        ((f, c) for f, c in contributions.items() if c > 0), key=lambda fc: fc[1], reverse=True
    )
    return [describe(f, row[f]) for f, _ in positive[:k]]
