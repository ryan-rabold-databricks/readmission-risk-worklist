"""Expected shape of each EHR extract entity (JSON lines in ehr_raw.ehr_landing).

Fields that do not match are captured in _rescued_data by Auto Loader and the row is
quarantined (rule ``schema_conforms``).
"""

from __future__ import annotations

_RECORD_TS = "record_created_ts TIMESTAMP, record_updated_ts TIMESTAMP, extract_date DATE"

SOURCE_SCHEMAS: dict[str, str] = {
    "patient": (
        "mrn STRING, first_name STRING, last_name STRING, birth_date DATE, sex STRING, "
        f"phone STRING, zip_code STRING, primary_payer STRING, {_RECORD_TS}"
    ),
    "encounter": (
        "encounter_number STRING, mrn STRING, facility_id STRING, encounter_type STRING, "
        "admission_type STRING, admit_ts TIMESTAMP, discharge_ts TIMESTAMP, "
        f"discharge_disposition STRING, drg_code STRING, {_RECORD_TS}"
    ),
    "diagnosis": (
        "encounter_number STRING, icd10_code STRING, dx_sequence INT, dx_type STRING, "
        f"{_RECORD_TS}"
    ),
    "appointment": (
        "appointment_number STRING, mrn STRING, source_encounter_number STRING, "
        f"scheduled_ts TIMESTAMP, provider_type STRING, status STRING, {_RECORD_TS}"
    ),
}
