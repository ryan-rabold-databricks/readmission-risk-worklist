# Refresh check: the pipeline and jobs write unmasked data under the project's own ABAC policies (#62, #60 failure mode)
# Refresh runs: refresh_1_source_simulator.log (7 extract dates), refresh_2_daily_cycle.log (worklist days 2026-11-07..13).
# The project's policies were first written 2026-11-09T02:05:53Z (c2_c5_governance_checks.raw.txt), so every row
# written after that was written by the exempt run-as identity while the masks applied to account users.
-- ### Rows written since the policies existed, and how many of them hold masked or redacted values (expect > 0 written, 0 masked)
SELECT 'clinical_silver.patient' t, count_if(audit_updated_at > TIMESTAMP'2026-11-09T02:05:53Z') written_after_policies,
       count_if(audit_updated_at > TIMESTAMP'2026-11-09T02:05:53Z' AND (first_name IN ('***', 'REDACTED') OR last_name IN ('***', 'REDACTED') OR mrn = '***' OR phone = '***' OR zip_code = '***')) masked_in_those,
       count_if(audit_updated_at > TIMESTAMP'2026-11-09T02:05:53Z' AND month(birth_date) = 1 AND day(birth_date) = 1) jan_1_birth_dates_in_those
FROM rtr_demo_catalog.clinical_silver.patient
UNION ALL SELECT 'readmission_worklist_gold.care_worklist', count_if(audit_updated_at > TIMESTAMP'2026-11-09T02:05:53Z'),
       count_if(audit_updated_at > TIMESTAMP'2026-11-09T02:05:53Z' AND (patient_display_name LIKE '%***%' OR patient_display_name LIKE '%REDACTED%' OR phone = '***')), NULL
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist
UNION ALL SELECT 'readmission_worklist_gold.care_worklist_synced (Lakebase copy via foreign table)', count_if(worklist_date >= DATE'2026-11-07'),
       count_if(worklist_date >= DATE'2026-11-07' AND (patient_display_name LIKE '%***%' OR patient_display_name LIKE '%REDACTED%' OR phone = '***')), NULL
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist_synced
-- ### New worklist days: items, distinct real names, briefs (expect names distinct and not masked)
SELECT worklist_date, count(*) items, count(DISTINCT patient_display_name) distinct_names,
       count_if(length(trim(outreach_brief)) >= 80) with_brief, min(audit_created_at) first_written
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist WHERE worklist_date >= DATE'2026-11-07' GROUP BY 1 ORDER BY 1
-- ### Every gold and silver table touched by the refresh, latest write time
SELECT 'clinical_silver.patient' t, max(audit_updated_at) latest_write FROM rtr_demo_catalog.clinical_silver.patient
UNION ALL SELECT 'clinical_silver.encounter', max(audit_updated_at) FROM rtr_demo_catalog.clinical_silver.encounter
UNION ALL SELECT 'readmission_worklist_gold.discharge_features', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.discharge_features
UNION ALL SELECT 'readmission_worklist_gold.readmission_outcome', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.readmission_outcome
UNION ALL SELECT 'readmission_worklist_gold.discharge_risk_score', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score
UNION ALL SELECT 'readmission_worklist_gold.care_worklist', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist
UNION ALL SELECT 'care_management_silver.app_audit_event', max(audit_updated_at) FROM rtr_demo_catalog.care_management_silver.app_audit_event
-- ### Tags survived the refresh (expect 28 phi_data_classification / row_filter_policy column tags, 0 class.*)
SELECT tag_name, count(*) n FROM rtr_demo_catalog.information_schema.column_tags
WHERE schema_name IN ('ehr_bronze', 'clinical_silver', 'care_management_silver', 'readmission_worklist_gold', 'readmission_worklist_app_bronze')
  AND (tag_name IN ('phi_data_classification', 'row_filter_policy') OR tag_name LIKE 'class.%')
GROUP BY 1 ORDER BY 1
-- ### Audit events now curated in silver (B6 lag closed)
SELECT event_name, count(*) n, max(event_ts) latest FROM rtr_demo_catalog.care_management_silver.app_audit_event GROUP BY 1 ORDER BY 1
