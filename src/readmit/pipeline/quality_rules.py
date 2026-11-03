"""Data-quality rules for bronze EHR records.

Each rule is a SQL predicate that must be TRUE for a valid row (NULL counts as a
failure). The same rules feed the bronze expectations (event-log metrics) and the
quarantine routing, so the two can never drift apart.
"""

from __future__ import annotations

from pyspark.sql import Column
from pyspark.sql import functions as F

_COMMON: dict[str, str] = {
    "record_timestamps_present": "record_created_ts IS NOT NULL AND record_updated_ts IS NOT NULL",
    "schema_conforms": "_rescued_data IS NULL",
}

RULES: dict[str, dict[str, str]] = {
    "patient": {
        "mrn_present": "mrn IS NOT NULL",
        "name_present": "first_name IS NOT NULL AND last_name IS NOT NULL",
        "birth_date_plausible": (
            "birth_date >= DATE'1900-01-01' AND birth_date <= to_date(record_updated_ts)"
        ),
        **_COMMON,
    },
    "encounter": {
        "encounter_number_present": "encounter_number IS NOT NULL",
        "mrn_present": "mrn IS NOT NULL",
        "facility_present": "facility_id IS NOT NULL",
        "encounter_type_valid": "encounter_type IN ('INPATIENT', 'ED')",
        "admit_ts_present": "admit_ts IS NOT NULL",
        "discharge_after_admit": "discharge_ts IS NULL OR discharge_ts >= admit_ts",
        **_COMMON,
    },
    "diagnosis": {
        "encounter_number_present": "encounter_number IS NOT NULL",
        "icd10_format": "icd10_code RLIKE '^[A-Z][0-9][0-9A-Z](\\\\.[0-9A-Z]{1,4})?$'",
        "dx_sequence_valid": "dx_sequence >= 1",
        **_COMMON,
    },
    "appointment": {
        "appointment_number_present": "appointment_number IS NOT NULL",
        "mrn_present": "mrn IS NOT NULL",
        "scheduled_ts_present": "scheduled_ts IS NOT NULL",
        "status_valid": "status IN ('SCHEDULED', 'COMPLETED', 'NO_SHOW', 'CANCELLED')",
        **_COMMON,
    },
}


def failed_rules(entity: str) -> Column:
    """ARRAY<STRING> of the rule names a row fails (empty when the row is valid)."""
    checks = [
        F.when(~F.coalesce(F.expr(condition), F.lit(False)), F.lit(name))
        for name, condition in RULES[entity].items()
    ]
    return F.filter(F.array(*checks), lambda c: c.isNotNull())
