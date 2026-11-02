# Phase 1 landing validation

Run against `/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing` on workspace `fevm-classic-stable` after the backfill run, 2026-11-02T17:21Z.

## Records, extract dates, and files per entity

```sql
SELECT 'patient' entity, count(*) records, count(DISTINCT extract_date) dates, count(DISTINCT _metadata.file_path) files FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/patient`
UNION ALL SELECT 'encounter', count(*), count(DISTINCT extract_date), count(DISTINCT _metadata.file_path) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/encounter`
UNION ALL SELECT 'diagnosis', count(*), count(DISTINCT extract_date), count(DISTINCT _metadata.file_path) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/diagnosis`
UNION ALL SELECT 'appointment', count(*), count(DISTINCT extract_date), count(DISTINCT _metadata.file_path) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/appointment`
```

```json
[
  {
    "dates": "731",
    "entity": "patient",
    "files": "731",
    "records": "71705"
  },
  {
    "dates": "731",
    "entity": "encounter",
    "files": "731",
    "records": "319407"
  },
  {
    "dates": "731",
    "entity": "diagnosis",
    "files": "731",
    "records": "488930"
  },
  {
    "dates": "731",
    "entity": "appointment",
    "files": "731",
    "records": "192117"
  }
]
```

## Injected bad rows and CDC records (encounter)

```sql
SELECT
  sum(CASE WHEN mrn IS NULL THEN 1 ELSE 0 END) null_mrn,
  sum(CASE WHEN discharge_ts < admit_ts THEN 1 ELSE 0 END) discharge_before_admit,
  count(*) - count(DISTINCT to_json(struct(*))) exact_duplicates,
  sum(CASE WHEN discharge_ts IS NULL THEN 1 ELSE 0 END) admit_only_records,
  count(DISTINCT encounter_number) distinct_encounters
FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/encounter`
```

```json
[
  {
    "admit_only_records": "114474",
    "discharge_before_admit": "193",
    "distinct_encounters": "204006",
    "exact_duplicates": "789",
    "null_mrn": "498"
  }
]
```

## Injected bad rows (diagnosis, patient, appointment)

```sql
SELECT
  (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/diagnosis` WHERE icd10_code LIKE '%#%') malformed_icd10,
  (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/patient` WHERE birth_date > current_date()) future_birth_date,
  (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/appointment` WHERE scheduled_ts IS NULL) null_scheduled_ts
```

```json
[
  {
    "future_birth_date": "148",
    "malformed_icd10": "1234",
    "null_scheduled_ts": "432"
  }
]
```

## Referential integrity: encounter MRNs without a patient record

```sql
SELECT count(*) AS encounter_mrns_missing_patient FROM (SELECT DISTINCT mrn FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/encounter` WHERE mrn IS NOT NULL) e LEFT ANTI JOIN (SELECT DISTINCT mrn FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/patient`) p USING (mrn)
```

```json
[
  {
    "encounter_mrns_missing_patient": "0"
  }
]
```

## Referential integrity: diagnoses without an encounter

```sql
SELECT count(*) AS dx_missing_encounter FROM (SELECT DISTINCT encounter_number FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/diagnosis`) d LEFT ANTI JOIN (SELECT DISTINCT encounter_number FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/encounter`) e USING (encounter_number)
```

```json
[
  {
    "dx_missing_encounter": "0"
  }
]
```

## Appointment status records (scheduled, then final status in a later extract)

```sql
SELECT status, count(*) n FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/appointment` GROUP BY status ORDER BY n DESC
```

```json
[
  {
    "n": "96489",
    "status": "SCHEDULED"
  },
  {
    "n": "74497",
    "status": "COMPLETED"
  },
  {
    "n": "18263",
    "status": "NO_SHOW"
  },
  {
    "n": "2868",
    "status": "CANCELLED"
  }
]
```

