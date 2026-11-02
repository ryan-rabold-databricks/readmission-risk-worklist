"""Clinical code reference shared by the source simulator and the silver pipeline.

The simulator emits ICD-10 codes only; silver derives ``condition_group`` and the
Charlson index from these tables, so both sides stay consistent.
"""

from __future__ import annotations

# Primary diagnosis codes per condition group. HRRP conditions first.
CONDITION_PRIMARY_CODES: dict[str, list[str]] = {
    "heart_failure": ["I50.23", "I50.33", "I50.9", "I11.0"],
    "copd": ["J44.1", "J44.0"],
    "pneumonia": ["J18.9", "J15.9", "J18.1"],
    "ami": ["I21.4", "I21.09", "I21.19"],
    "sepsis": ["A41.9", "A41.51", "A41.01"],
    "diabetes": ["E11.65", "E11.10", "E10.10"],
    "ortho_surgery": ["M17.11", "M16.11", "S72.001A"],
    "gi": ["K92.2", "K57.32", "K85.90"],
    "other": ["N39.0", "I48.91", "R55", "K80.10"],
}

# Treat-and-release ED visit primary codes.
ED_PRIMARY_CODES: dict[str, list[str]] = {
    "chest_pain": ["R07.9", "R07.89"],
    "respiratory": ["J06.9", "J44.1", "R06.02"],
    "abdominal_pain": ["R10.9", "R10.31"],
    "heart_failure": ["I50.9"],
    "injury": ["S93.401A", "S61.411A", "S09.90XA"],
    "other": ["R51.9", "R42", "N39.0"],
}

# ICD-10 prefix to condition group, longest prefix wins (used by silver).
CONDITION_GROUP_PREFIXES: dict[str, str] = {
    "I50": "heart_failure",
    "I11.0": "heart_failure",
    "J44": "copd",
    "J18": "pneumonia",
    "J15": "pneumonia",
    "I21": "ami",
    "A41": "sepsis",
    "E10": "diabetes",
    "E11": "diabetes",
    "M16": "ortho_surgery",
    "M17": "ortho_surgery",
    "S72": "ortho_surgery",
    "K92": "gi",
    "K57": "gi",
    "K85": "gi",
}

# Charlson comorbidity categories (Quan ICD-10 coding, simplified): (representative
# code the simulator emits, ICD-10 prefixes silver matches, Charlson weight).
CHARLSON_CATEGORIES: dict[str, tuple[str, tuple[str, ...], int]] = {
    "congestive_heart_failure": ("I50.9", ("I50", "I11.0"), 1),
    "myocardial_infarction": ("I25.2", ("I21", "I22", "I25.2"), 1),
    "peripheral_vascular": ("I73.9", ("I70", "I71", "I73.9"), 1),
    "cerebrovascular": ("I63.9", ("I63", "I69", "G45"), 1),
    "dementia": ("F03.90", ("F01", "F02", "F03", "G30"), 1),
    "chronic_pulmonary": ("J44.9", ("J44", "J45", "J47"), 1),
    "rheumatic": ("M06.9", ("M05", "M06", "M32"), 1),
    "peptic_ulcer": ("K27.9", ("K25", "K26", "K27"), 1),
    "mild_liver": ("K70.30", ("K70.3", "K73", "K74.6"), 1),
    "diabetes_uncomplicated": (
        "E11.9",
        ("E10.0", "E10.1", "E10.6", "E10.8", "E10.9", "E11.0", "E11.1", "E11.6", "E11.8", "E11.9"),
        1,
    ),
    "diabetes_complicated": (
        "E11.22",
        ("E10.2", "E10.3", "E10.4", "E10.5", "E10.7", "E11.2", "E11.3", "E11.4", "E11.5", "E11.7"),
        2,
    ),
    "hemiplegia": ("G81.90", ("G81", "G82"), 2),
    "renal": ("N18.4", ("N18.4", "N18.5", "N18.6"), 2),
    "malignancy": ("C34.90", ("C18", "C34", "C50", "C61"), 2),
    "moderate_severe_liver": ("K72.10", ("K72.1", "K76.6"), 3),
    "metastatic_tumor": ("C78.00", ("C77", "C78", "C79"), 6),
}

# Common non-Charlson secondary codes.
COMMON_SECONDARY_CODES: list[str] = ["I10", "E78.5", "F32.9", "Z87.891", "E66.9"]

DRG_BY_CONDITION: dict[str, str] = {
    "heart_failure": "291",
    "copd": "190",
    "pneumonia": "193",
    "ami": "280",
    "sepsis": "871",
    "diabetes": "638",
    "ortho_surgery": "470",
    "gi": "392",
    "other": "690",
}


def condition_group_for(icd10_code: str) -> str | None:
    """Map an ICD-10 code to its condition group by longest matching prefix."""
    matches = [p for p in CONDITION_GROUP_PREFIXES if icd10_code.startswith(p)]
    return CONDITION_GROUP_PREFIXES[max(matches, key=len)] if matches else None
