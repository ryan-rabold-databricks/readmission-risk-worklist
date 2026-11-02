"""Synthetic EHR source simulator configuration.

The story the data tells (approved 2026-11-02):
- A five-hospital system with a ~16% 30-day readmission rate.
- Riverbend Community Hospital (rural) completes far fewer 7-day follow-ups and
  readmits ~21% of discharges.
- Heart failure patients discharged without a 7-day follow-up readmit far more
  often than those who get one.
- A winter respiratory surge (Dec-Feb) raises COPD and pneumonia volume and risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class FacilityProfile:
    facility_id: str
    volume_share: float
    followup_scheduled_rate: float  # P(any follow-up scheduled at discharge)
    followup_within_7d_rate: float  # P(appointment within 7 days | scheduled)
    followup_completion_rate: float  # P(patient attends | scheduled)
    readmit_logit_effect: float
    zip_prefix: str
    area_code: str


# facility_id values must match seeds/facility.csv (enforced by tests).
FACILITIES: tuple[FacilityProfile, ...] = (
    FacilityProfile("FAC-LMC", 0.34, 0.90, 0.76, 0.84, 0.00, "432", "614"),
    FacilityProfile("FAC-NGR", 0.24, 0.88, 0.74, 0.83, 0.00, "430", "740"),
    FacilityProfile("FAC-SVH", 0.20, 0.86, 0.72, 0.82, 0.05, "431", "380"),
    FacilityProfile("FAC-CCH", 0.12, 0.86, 0.72, 0.82, 0.00, "433", "220"),
    FacilityProfile("FAC-RCH", 0.10, 0.72, 0.55, 0.75, 0.60, "457", "937"),
)

# condition -> (base weight, frailty coef, winter mult, summer mult, age>=65 mult)
CONDITION_MIX: dict[str, tuple[float, float, float, float, float]] = {
    "heart_failure": (0.12, 0.35, 1.10, 0.95, 1.40),
    "copd": (0.09, 0.30, 1.60, 0.80, 1.20),
    "pneumonia": (0.09, 0.20, 1.50, 0.80, 1.20),
    "ami": (0.05, 0.10, 1.05, 1.00, 1.20),
    "sepsis": (0.08, 0.20, 1.10, 1.00, 1.10),
    "diabetes": (0.06, 0.10, 1.00, 1.00, 0.90),
    "ortho_surgery": (0.12, -0.30, 0.90, 1.05, 1.10),
    "gi": (0.11, 0.00, 1.00, 1.00, 1.00),
    "other": (0.28, 0.00, 1.00, 1.00, 1.00),
}

EMERGENT_RATE: dict[str, float] = {
    "heart_failure": 0.90,
    "copd": 0.92,
    "pneumonia": 0.90,
    "ami": 0.97,
    "sepsis": 0.97,
    "diabetes": 0.85,
    "ortho_surgery": 0.15,
    "gi": 0.80,
    "other": 0.60,
}

MEDIAN_LOS_DAYS: dict[str, float] = {
    "heart_failure": 4.5,
    "copd": 4.0,
    "pneumonia": 4.5,
    "ami": 3.5,
    "sepsis": 6.5,
    "diabetes": 3.0,
    "ortho_surgery": 2.5,
    "gi": 3.5,
    "other": 3.0,
}

# ED treat-and-release mix: group -> (base weight, frailty coef, winter mult)
ED_MIX: dict[str, tuple[float, float, float]] = {
    "chest_pain": (0.20, 0.10, 1.00),
    "respiratory": (0.20, 0.20, 1.50),
    "abdominal_pain": (0.18, 0.00, 1.00),
    "heart_failure": (0.06, 0.40, 1.10),
    "injury": (0.20, -0.20, 0.90),
    "other": (0.16, 0.00, 1.00),
}

# Charlson category -> (intercept, frailty coef, per-decade-over-65 coef) for the
# patient-level probability of carrying the comorbidity.
COMORBIDITY_LOGIT: dict[str, tuple[float, float, float]] = {
    "congestive_heart_failure": (-2.6, 0.9, 0.35),
    "myocardial_infarction": (-3.0, 0.6, 0.30),
    "peripheral_vascular": (-3.4, 0.6, 0.30),
    "cerebrovascular": (-3.3, 0.6, 0.35),
    "dementia": (-4.0, 0.6, 0.70),
    "chronic_pulmonary": (-2.4, 0.7, 0.20),
    "rheumatic": (-3.8, 0.3, 0.00),
    "peptic_ulcer": (-4.2, 0.3, 0.00),
    "mild_liver": (-4.0, 0.5, -0.10),
    "diabetes_uncomplicated": (-1.6, 0.4, 0.10),
    "diabetes_complicated": (-2.9, 0.7, 0.15),
    "hemiplegia": (-4.6, 0.5, 0.10),
    "renal": (-2.9, 0.8, 0.30),
    "malignancy": (-3.2, 0.5, 0.30),
    "moderate_severe_liver": (-5.2, 0.6, 0.00),
    "metastatic_tumor": (-4.6, 0.5, 0.20),
}


@dataclass(frozen=True)
class ReadmitModel:
    """Logistic ground truth for planned 30-day readmissions of index stays."""

    intercept: float = -2.88
    frailty: float = 0.45
    los_per_day: float = 0.06  # capped at 15 days
    emergent: float = 0.35
    medicaid: float = 0.15
    winter_respiratory: float = 0.40
    followup_7d: float = -0.70
    followup_7d_heart_failure: float = -1.00
    condition: dict[str, float] = field(
        default_factory=lambda: {
            "heart_failure": 0.55,
            "copd": 0.35,
            "pneumonia": 0.20,
            "ami": 0.15,
            "sepsis": 0.30,
            "diabetes": 0.20,
            "ortho_surgery": -0.60,
            "gi": 0.00,
            "other": -0.10,
        }
    )
    disposition: dict[str, float] = field(
        default_factory=lambda: {
            "HOME": 0.00,
            "HOME_HEALTH": 0.10,
            "SNF": 0.25,
            "REHAB": 0.00,
            "AMA": 0.70,
            "HOSPICE": 0.00,
        }
    )


@dataclass(frozen=True)
class SimulatorConfig:
    history_start: date
    run_date: date
    seed: int = 20261102
    n_patients: int = 80_000
    inpatient_per_day: float = 140.0
    ed_per_day: float = 120.0
    bad_row_rate: float = 0.005
    readmit: ReadmitModel = field(default_factory=ReadmitModel)

    def __post_init__(self) -> None:
        if self.run_date < self.history_start:
            raise ValueError(
                f"run_date {self.run_date} is before history_start {self.history_start}"
            )


FEMALE_FIRST_NAMES = (
    "Mary Patricia Linda Barbara Elizabeth Jennifer Maria Susan Margaret Dorothy Lisa Nancy "
    "Karen Betty Helen Sandra Donna Carol Ruth Sharon Michelle Laura Sarah Kimberly Deborah "
    "Jessica Shirley Cynthia Angela Melissa Brenda Amy Anna Rebecca Virginia Kathleen Pamela "
    "Martha Debra Amanda Stephanie Carolyn Christine Marie Janet Catherine Frances Ann Joyce Diane "
    "Rosa Gloria Yolanda Mei Aisha Priya Fatima Keisha Lucia Nadia"
).split()

MALE_FIRST_NAMES = (
    "James John Robert Michael William David Richard Charles Joseph Thomas Christopher Daniel "
    "Paul Mark Donald George Kenneth Steven Edward Brian Ronald Anthony Kevin Jason Matthew Gary "
    "Timothy Jose Larry Jeffrey Frank Scott Eric Stephen Andrew Raymond Gregory Joshua Jerry "
    "Dennis Walter Patrick Peter Harold Douglas Henry Carl Arthur Ryan Roger Luis Carlos Wei "
    "Omar Rahul Darnell Andre Miguel Tariq"
).split()

LAST_NAMES = (
    "Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez "
    "Gonzalez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris "
    "Sanchez Clark Ramirez Lewis Robinson Walker Young Allen King Wright Scott Torres Nguyen Hill "
    "Flores Green Adams Nelson Baker Hall Rivera Campbell Mitchell Carter Roberts Gomez Phillips "
    "Evans Turner Diaz Parker Cruz Edwards Collins Reyes Stewart Morris Morales Murphy Cook Rogers "
    "Gutierrez Ortiz Morgan Cooper Peterson Bailey Reed Kelly Howard Ramos Kim Cox Ward Richardson "
    "Watson Brooks Chavez Wood James Bennett Gray Mendoza Ruiz Hughes Price Alvarez Castillo "
    "Sanders Patel Myers Long Ross Foster Jimenez Okafor Shah Chen"
).split()
