# Phase 2 pipeline run: dev_readmit_pipeline

Workspace `fevm-classic-stable`, catalog `rtr_demo_catalog`, generated 2026-11-03T18:29Z. Source: the pipeline event log table `rtr_demo_catalog.ehr_bronze.event_log_681e67de_8388_473c_95d2_56d9e3aa606f`.

## Updates

Update 2ea751 failed on the `--editable` install (`ModuleNotFoundError: readmit`, DECISIONS.md #24). Update b789d7 processed all flows, then failed while applying foreign-key constraints. 896b85 completed after the FKs were removed (DECISIONS.md #25), and 48345f is the rerun after the primary_condition_group fix. A later update, 56feb0 (COMPLETED, after this file was generated), switched the package import to `root_path` (DECISIONS.md #24); row counts were unchanged.

```sql
SELECT origin.update_id, min(timestamp) started, max(timestamp) ended, max_by(details:update_progress.state, timestamp) final_state
FROM rtr_demo_catalog.ehr_bronze.event_log_681e67de_8388_473c_95d2_56d9e3aa606f WHERE event_type = 'update_progress' GROUP BY 1 ORDER BY started
```

```json
[
  {
    "ended": "2026-11-03T18:17:39.853Z",
    "final_state": "FAILED",
    "started": "2026-11-03T18:16:58.185Z",
    "update_id": "2ea7519b-83cb-471b-b13b-f28a252f20d6"
  },
  {
    "ended": "2026-11-03T18:21:33.818Z",
    "final_state": "FAILED",
    "started": "2026-11-03T18:19:21.881Z",
    "update_id": "b789d7af-467f-42da-8247-94fd7ae89f4d"
  },
  {
    "ended": "2026-11-03T18:24:29.619Z",
    "final_state": "COMPLETED",
    "started": "2026-11-03T18:23:19.879Z",
    "update_id": "896b8577-4bba-4154-9667-5c8d6a93c77e"
  },
  {
    "ended": "2026-11-03T18:28:20.278Z",
    "final_state": "COMPLETED",
    "started": "2026-11-03T18:27:20.841Z",
    "update_id": "48345f29-2d2a-496e-96a5-41e6965568a8"
  }
]
```

## Rows written per flow (all updates)

```sql
SELECT origin.flow_name, sum(CAST(details:flow_progress.metrics.num_output_rows AS BIGINT)) rows_written
FROM rtr_demo_catalog.ehr_bronze.event_log_681e67de_8388_473c_95d2_56d9e3aa606f WHERE event_type = 'flow_progress' AND details:flow_progress.metrics.num_output_rows IS NOT NULL
GROUP BY 1 ORDER BY 1
```

```json
[
  {
    "flow_name": "rtr_demo_catalog.care_management_silver.care_team_assignment",
    "rows_written": "15"
  },
  {
    "flow_name": "rtr_demo_catalog.care_management_silver.risk_tier_policy",
    "rows_written": "9"
  },
  {
    "flow_name": "rtr_demo_catalog.clinical_silver.facility",
    "rows_written": "15"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.appointment_raw",
    "rows_written": "192397"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.diagnosis_raw",
    "rows_written": "489474"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "rows_written": "319919"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.patient_raw",
    "rows_written": "71753"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.quarantine_appointment",
    "rows_written": "441"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.quarantine_diagnosis",
    "rows_written": "1138"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.quarantine_encounter",
    "rows_written": "737"
  },
  {
    "flow_name": "rtr_demo_catalog.ehr_bronze.quarantine_patient",
    "rows_written": "169"
  },
  {
    "flow_name": "rtr_demo_catalog.readmission_worklist_gold.discharge_features",
    "rows_written": "338271"
  }
]
```

## Bronze expectations (warn-only; failing rows are routed to quarantine_raw)

```sql
SELECT origin.flow_name, e.name expectation, sum(e.passed_records) passed, sum(e.failed_records) failed
FROM rtr_demo_catalog.ehr_bronze.event_log_681e67de_8388_473c_95d2_56d9e3aa606f LATERAL VIEW explode(from_json(details:flow_progress.data_quality.expectations, 'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) t AS e
WHERE event_type = 'flow_progress' GROUP BY 1,2 HAVING sum(e.passed_records) + sum(e.failed_records) > 0 ORDER BY 1,2
```

```json
[
  {
    "expectation": "capacity_positive",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.care_management_silver.care_team_assignment",
    "passed": "15"
  },
  {
    "expectation": "score_range_valid",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.care_management_silver.risk_tier_policy",
    "passed": "9"
  },
  {
    "expectation": "appointment_number_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.appointment_raw",
    "passed": "192397"
  },
  {
    "expectation": "mrn_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.appointment_raw",
    "passed": "192397"
  },
  {
    "expectation": "record_timestamps_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.appointment_raw",
    "passed": "192397"
  },
  {
    "expectation": "scheduled_ts_present",
    "failed": "441",
    "flow_name": "rtr_demo_catalog.ehr_bronze.appointment_raw",
    "passed": "191956"
  },
  {
    "expectation": "schema_conforms",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.appointment_raw",
    "passed": "192397"
  },
  {
    "expectation": "status_valid",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.appointment_raw",
    "passed": "192397"
  },
  {
    "expectation": "dx_sequence_valid",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.diagnosis_raw",
    "passed": "489474"
  },
  {
    "expectation": "encounter_number_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.diagnosis_raw",
    "passed": "489474"
  },
  {
    "expectation": "icd10_format",
    "failed": "1138",
    "flow_name": "rtr_demo_catalog.ehr_bronze.diagnosis_raw",
    "passed": "488336"
  },
  {
    "expectation": "record_timestamps_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.diagnosis_raw",
    "passed": "489474"
  },
  {
    "expectation": "schema_conforms",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.diagnosis_raw",
    "passed": "489474"
  },
  {
    "expectation": "admit_ts_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319919"
  },
  {
    "expectation": "discharge_after_admit",
    "failed": "226",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319693"
  },
  {
    "expectation": "encounter_number_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319919"
  },
  {
    "expectation": "encounter_type_valid",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319919"
  },
  {
    "expectation": "facility_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319919"
  },
  {
    "expectation": "mrn_present",
    "failed": "511",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319408"
  },
  {
    "expectation": "record_timestamps_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319919"
  },
  {
    "expectation": "schema_conforms",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.encounter_raw",
    "passed": "319919"
  },
  {
    "expectation": "birth_date_plausible",
    "failed": "169",
    "flow_name": "rtr_demo_catalog.ehr_bronze.patient_raw",
    "passed": "71584"
  },
  {
    "expectation": "mrn_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.patient_raw",
    "passed": "71753"
  },
  {
    "expectation": "name_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.patient_raw",
    "passed": "71753"
  },
  {
    "expectation": "record_timestamps_present",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.patient_raw",
    "passed": "71753"
  },
  {
    "expectation": "schema_conforms",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.ehr_bronze.patient_raw",
    "passed": "71753"
  },
  {
    "expectation": "age_plausible",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.readmission_worklist_gold.discharge_features",
    "passed": "338271"
  },
  {
    "expectation": "label_only_when_matured",
    "failed": "0",
    "flow_name": "rtr_demo_catalog.readmission_worklist_gold.discharge_features",
    "passed": "338271"
  }
]
```

