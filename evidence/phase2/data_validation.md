# Phase 2 data validation

Run on `fevm-classic-stable` after pipeline update 48345f, 2026-11-03T18:29Z.

## Bronze row counts equal landed records (no loss, no double ingestion)

```sql
SELECT 'patient' e, (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/patient`) landed, (SELECT count(*) FROM rtr_demo_catalog.ehr_bronze.patient_raw) bronze
UNION ALL SELECT 'encounter', (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/encounter`), (SELECT count(*) FROM rtr_demo_catalog.ehr_bronze.encounter_raw)
UNION ALL SELECT 'diagnosis', (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/diagnosis`), (SELECT count(*) FROM rtr_demo_catalog.ehr_bronze.diagnosis_raw)
UNION ALL SELECT 'appointment', (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/appointment`), (SELECT count(*) FROM rtr_demo_catalog.ehr_bronze.appointment_raw)
```

```json
[
  {
    "bronze": "71753",
    "e": "patient",
    "landed": "71753"
  },
  {
    "bronze": "319919",
    "e": "encounter",
    "landed": "319919"
  },
  {
    "bronze": "489474",
    "e": "diagnosis",
    "landed": "489474"
  },
  {
    "bronze": "192397",
    "e": "appointment",
    "landed": "192397"
  }
]
```

## Quarantine by entity and rule

```sql
SELECT entity, rule, count(*) n FROM rtr_demo_catalog.ehr_bronze.quarantine_raw LATERAL VIEW explode(failed_rules) t AS rule GROUP BY 1,2 ORDER BY 1,2
```

```json
[
  {
    "entity": "appointment",
    "n": "441",
    "rule": "scheduled_ts_present"
  },
  {
    "entity": "diagnosis",
    "n": "1138",
    "rule": "icd10_format"
  },
  {
    "entity": "encounter",
    "n": "226",
    "rule": "discharge_after_admit"
  },
  {
    "entity": "encounter",
    "n": "511",
    "rule": "mrn_present"
  },
  {
    "entity": "patient",
    "n": "169",
    "rule": "birth_date_plausible"
  }
]
```

## Quarantine precision: injected bad rows vs quarantined rows

```sql
SELECT
 (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/diagnosis` WHERE icd10_code LIKE '%#%') injected_bad_icd10,
 (SELECT count(*) FROM rtr_demo_catalog.ehr_bronze.quarantine_raw WHERE entity = 'diagnosis') quarantined_diagnosis,
 (SELECT count(*) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/encounter` WHERE mrn IS NULL OR discharge_ts < admit_ts) injected_bad_encounter,
 (SELECT count(*) FROM rtr_demo_catalog.ehr_bronze.quarantine_raw WHERE entity = 'encounter') quarantined_encounter
```

```json
[
  {
    "injected_bad_encounter": "737",
    "injected_bad_icd10": "1138",
    "quarantined_diagnosis": "1138",
    "quarantined_encounter": "737"
  }
]
```

## AUTO CDC: one silver row per distinct valid source key; updates applied

```sql
SELECT
 (SELECT count(DISTINCT encounter_number) FROM json.`/Volumes/rtr_demo_catalog/ehr_raw/ehr_landing/encounter` WHERE mrn IS NOT NULL AND NOT discharge_ts < admit_ts OR (mrn IS NOT NULL AND discharge_ts IS NULL)) distinct_valid_encounters,
 (SELECT count(*) FROM rtr_demo_catalog.clinical_silver.encounter) silver_encounters,
 (SELECT count(*) FROM rtr_demo_catalog.clinical_silver.encounter WHERE encounter_type = 'INPATIENT' AND discharge_ts IS NULL) inpatient_still_admitted,
 (SELECT count(*) FROM rtr_demo_catalog.clinical_silver.follow_up_appointment WHERE status = 'SCHEDULED') appointments_still_scheduled
```

```json
[
  {
    "appointments_still_scheduled": "893",
    "distinct_valid_encounters": "204278",
    "inpatient_still_admitted": "83",
    "silver_encounters": "204278"
  }
]
```

## Silver and gold row counts with primary-key uniqueness

```sql
SELECT 'clinical_silver.patient' t, count(*) n, count(DISTINCT patient_id) distinct_pk FROM rtr_demo_catalog.clinical_silver.patient
UNION ALL SELECT 'clinical_silver.encounter', count(*), count(DISTINCT encounter_id) FROM rtr_demo_catalog.clinical_silver.encounter
UNION ALL SELECT 'clinical_silver.diagnosis', count(*), count(DISTINCT diagnosis_id) FROM rtr_demo_catalog.clinical_silver.diagnosis
UNION ALL SELECT 'clinical_silver.follow_up_appointment', count(*), count(DISTINCT appointment_id) FROM rtr_demo_catalog.clinical_silver.follow_up_appointment
UNION ALL SELECT 'clinical_silver.facility', count(*), count(DISTINCT facility_id) FROM rtr_demo_catalog.clinical_silver.facility
UNION ALL SELECT 'care_management_silver.risk_tier_policy', count(*), count(DISTINCT risk_tier) FROM rtr_demo_catalog.care_management_silver.risk_tier_policy
UNION ALL SELECT 'care_management_silver.care_team_assignment', count(*), count(DISTINCT assignment_id) FROM rtr_demo_catalog.care_management_silver.care_team_assignment
UNION ALL SELECT 'readmission_worklist_gold.discharge_features', count(*), count(DISTINCT encounter_id) FROM rtr_demo_catalog.readmission_worklist_gold.discharge_features
```

```json
[
  {
    "distinct_pk": "69012",
    "n": "69012",
    "t": "clinical_silver.patient"
  },
  {
    "distinct_pk": "204278",
    "n": "204278",
    "t": "clinical_silver.encounter"
  },
  {
    "distinct_pk": "487160",
    "n": "487160",
    "t": "clinical_silver.diagnosis"
  },
  {
    "distinct_pk": "96188",
    "n": "96188",
    "t": "clinical_silver.follow_up_appointment"
  },
  {
    "distinct_pk": "5",
    "n": "5",
    "t": "clinical_silver.facility"
  },
  {
    "distinct_pk": "3",
    "n": "3",
    "t": "care_management_silver.risk_tier_policy"
  },
  {
    "distinct_pk": "5",
    "n": "5",
    "t": "care_management_silver.care_team_assignment"
  },
  {
    "distinct_pk": "112757",
    "n": "112757",
    "t": "readmission_worklist_gold.discharge_features"
  }
]
```

## Primary-key constraints (informational)

```sql
SELECT table_schema, table_name, constraint_name, constraint_type FROM rtr_demo_catalog.information_schema.table_constraints WHERE table_schema IN ('clinical_silver','care_management_silver','readmission_worklist_gold') ORDER BY 1,2
```

```json
[
  {
    "constraint_name": "care_team_assignment_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "care_team_assignment",
    "table_schema": "care_management_silver"
  },
  {
    "constraint_name": "risk_tier_policy_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "risk_tier_policy",
    "table_schema": "care_management_silver"
  },
  {
    "constraint_name": "diagnosis_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "diagnosis",
    "table_schema": "clinical_silver"
  },
  {
    "constraint_name": "encounter_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "encounter",
    "table_schema": "clinical_silver"
  },
  {
    "constraint_name": "facility_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "facility",
    "table_schema": "clinical_silver"
  },
  {
    "constraint_name": "follow_up_appointment_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "follow_up_appointment",
    "table_schema": "clinical_silver"
  },
  {
    "constraint_name": "patient_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "patient",
    "table_schema": "clinical_silver"
  },
  {
    "constraint_name": "discharge_features_pk",
    "constraint_type": "PRIMARY KEY",
    "table_name": "discharge_features",
    "table_schema": "readmission_worklist_gold"
  }
]
```

## Gold discharge_features: label and feature profile

```sql
SELECT count(*) discharges, count(readmit_30d) matured_labels,
 round(avg(CAST(readmit_30d AS INT)), 4) readmit_30d_rate,
 round(avg(CAST(followup_scheduled_7d AS INT)), 4) followup_scheduled_7d_rate,
 round(avg(CAST(followup_within_7d AS INT)), 4) followup_within_7d_rate,
 round(avg(age_at_discharge), 1) avg_age, round(avg(length_of_stay_days), 2) avg_los_days,
 round(avg(CAST(emergent_admission AS INT)), 3) emergent_rate, round(avg(charlson_index), 2) avg_charlson,
 round(avg(ed_visits_6m), 2) avg_ed_visits_6m, round(avg(inpatient_admits_12m), 2) avg_inpatient_admits_12m,
 max(discharge_date) latest_discharge, max(label_matured_at) latest_label_matured_at
 FROM rtr_demo_catalog.readmission_worklist_gold.discharge_features
```

```json
[
  {
    "avg_age": "59.9",
    "avg_charlson": "1.61",
    "avg_ed_visits_6m": "0.32",
    "avg_inpatient_admits_12m": "0.77",
    "avg_los_days": "4.7",
    "discharges": "112757",
    "emergent_rate": "0.76",
    "followup_scheduled_7d_rate": "0.5874",
    "followup_within_7d_rate": "0.4666",
    "latest_discharge": "2026-11-02",
    "latest_label_matured_at": "2026-11-02T17:44:00.000Z",
    "matured_labels": "108185",
    "readmit_30d_rate": "0.1478"
  }
]
```

## Story: readmission and 7-day follow-up by facility (matured labels)

```sql
SELECT facility_id, count(*) matured, round(avg(CAST(readmit_30d AS INT)), 3) readmit_30d_rate, round(avg(CAST(followup_within_7d AS INT)), 3) followup_within_7d_rate
 FROM rtr_demo_catalog.readmission_worklist_gold.discharge_features WHERE readmit_30d IS NOT NULL GROUP BY 1 ORDER BY 1
```

```json
[
  {
    "facility_id": "FAC-CCH",
    "followup_within_7d_rate": "0.459",
    "matured": "13211",
    "readmit_30d_rate": "0.147"
  },
  {
    "facility_id": "FAC-LMC",
    "followup_within_7d_rate": "0.525",
    "matured": "36335",
    "readmit_30d_rate": "0.138"
  },
  {
    "facility_id": "FAC-NGR",
    "followup_within_7d_rate": "0.49",
    "matured": "25458",
    "readmit_30d_rate": "0.138"
  },
  {
    "facility_id": "FAC-RCH",
    "followup_within_7d_rate": "0.275",
    "matured": "11330",
    "readmit_30d_rate": "0.201"
  },
  {
    "facility_id": "FAC-SVH",
    "followup_within_7d_rate": "0.459",
    "matured": "21851",
    "readmit_30d_rate": "0.148"
  }
]
```

## Story: heart failure readmission by follow-up booked vs attended

```sql
SELECT followup_scheduled_7d, followup_within_7d, count(*) n, round(avg(CAST(readmit_30d AS INT)), 3) readmit_30d_rate
 FROM rtr_demo_catalog.readmission_worklist_gold.discharge_features WHERE readmit_30d IS NOT NULL AND primary_condition_group = 'heart_failure' GROUP BY 1,2 ORDER BY 1,2
```

```json
[
  {
    "followup_scheduled_7d": "false",
    "followup_within_7d": "false",
    "n": "6414",
    "readmit_30d_rate": "0.254"
  },
  {
    "followup_scheduled_7d": "true",
    "followup_within_7d": "false",
    "n": "2019",
    "readmit_30d_rate": "0.237"
  },
  {
    "followup_scheduled_7d": "true",
    "followup_within_7d": "true",
    "n": "7102",
    "readmit_30d_rate": "0.13"
  }
]
```

## Story: readmission by primary condition group

```sql
SELECT primary_condition_group, count(*) n, round(avg(CAST(readmit_30d AS INT)), 3) readmit_30d_rate
 FROM rtr_demo_catalog.readmission_worklist_gold.discharge_features WHERE readmit_30d IS NOT NULL GROUP BY 1 ORDER BY 3 DESC
```

```json
[
  {
    "n": "11549",
    "primary_condition_group": "copd",
    "readmit_30d_rate": "0.2"
  },
  {
    "n": "15535",
    "primary_condition_group": "heart_failure",
    "readmit_30d_rate": "0.195"
  },
  {
    "n": "8876",
    "primary_condition_group": "sepsis",
    "readmit_30d_rate": "0.187"
  },
  {
    "n": "10753",
    "primary_condition_group": "pneumonia",
    "readmit_30d_rate": "0.179"
  },
  {
    "n": "5482",
    "primary_condition_group": "ami",
    "readmit_30d_rate": "0.148"
  },
  {
    "n": "5845",
    "primary_condition_group": "diabetes",
    "readmit_30d_rate": "0.144"
  },
  {
    "n": "10678",
    "primary_condition_group": "gi",
    "readmit_30d_rate": "0.129"
  },
  {
    "n": "27354",
    "primary_condition_group": "other",
    "readmit_30d_rate": "0.114"
  },
  {
    "n": "12113",
    "primary_condition_group": "ortho_surgery",
    "readmit_30d_rate": "0.077"
  }
]
```

