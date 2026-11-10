# C2-C5: governance claims that had no committed text evidence
# C2 exempt identity reads real values (#62); C3 root cause of the redaction incident (#60);
# C4 leadership test functions (#65); C5 care_team_assignment profile and gold event_log tables (#67).
# Run as the pipeline run-as identity (the author in dev), the one principal the ABAC policies exempt.
-- ### C2: project ABAC policy writes (audit log; the job upserts all 12 policies on every run, logged as updatePolicy)
SELECT request_params.name AS policy_name, action_name, count(*) events, min(event_time) first_event, max(event_time) last_event,
       collect_set(user_identity.email) by_principal, collect_set(response.status_code) status_codes
FROM system.access.audit
WHERE event_date BETWEEN '2026-11-08' AND '2026-11-10' AND service_name = 'unityCatalog'
  AND action_name IN ('createPolicy', 'updatePolicy', 'deletePolicy') AND request_params.name LIKE 'readmit_%'
GROUP BY 1, 2 ORDER BY 1, 2
-- ### C2: exempt identity reads unmasked values in every masked schema (0 masked rows expected)
SELECT 'ehr_bronze.patient_raw' t, count(*) n, count_if(first_name = '***' OR mrn = '***' OR phone = '***') masked,
       count(DISTINCT first_name) distinct_first, round(avg(CAST(month(birth_date) = 1 AND day(birth_date) = 1 AS INT)), 4) share_jan_1
FROM rtr_demo_catalog.ehr_bronze.patient_raw
UNION ALL SELECT 'clinical_silver.patient', count(*), count_if(first_name = '***' OR last_name = '***' OR mrn = '***' OR phone = '***' OR zip_code = '***'),
       count(DISTINCT first_name), round(avg(CAST(month(birth_date) = 1 AND day(birth_date) = 1 AS INT)), 4)
FROM rtr_demo_catalog.clinical_silver.patient
UNION ALL SELECT 'readmission_worklist_gold.care_worklist', count(*), count_if(patient_display_name = '***' OR phone = '***'), count(DISTINCT patient_display_name), NULL
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist
UNION ALL SELECT 'readmission_worklist_gold.care_worklist_active (view)', count(*), count_if(patient_display_name = '***' OR phone = '***'), count(DISTINCT patient_display_name), NULL
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist_active
UNION ALL SELECT 'readmission_worklist_gold.care_worklist_synced (foreign)', count(*), count_if(patient_display_name = '***' OR phone = '***'), count(DISTINCT patient_display_name), NULL
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist_synced
-- ### C2: exempt identity is not row-filtered (all five facilities visible)
SELECT 'readmission_outcome' t, count(*) n, count(DISTINCT facility_id) facilities FROM rtr_demo_catalog.readmission_worklist_gold.readmission_outcome
UNION ALL SELECT 'care_worklist', count(*), count(DISTINCT facility_id) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist
UNION ALL SELECT 'clinical_silver.encounter', count(*), count(DISTINCT facility_id) FROM rtr_demo_catalog.clinical_silver.encounter
-- ### C2: latest pipeline and job writes vs policy creation (writes after the policies would prove the write path)
SELECT 'clinical_silver.patient' t, max(audit_updated_at) latest_write FROM rtr_demo_catalog.clinical_silver.patient
UNION ALL SELECT 'clinical_silver.encounter', max(audit_updated_at) FROM rtr_demo_catalog.clinical_silver.encounter
UNION ALL SELECT 'readmission_worklist_gold.discharge_features', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.discharge_features
UNION ALL SELECT 'readmission_worklist_gold.readmission_outcome', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.readmission_outcome
UNION ALL SELECT 'readmission_worklist_gold.discharge_risk_score', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score
UNION ALL SELECT 'readmission_worklist_gold.care_worklist', max(audit_updated_at) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist
-- ### C3: tag assignments on project tables carrying class.* tags, 2026-11-03 to 2026-11-09 (audit log)
SELECT event_time, action_name, user_identity.email AS principal, response.status_code,
       request_params.securable_full_name, request_params.subentity_name, request_params.changes
FROM system.access.audit
WHERE event_date BETWEEN '2026-11-03' AND '2026-11-09' AND service_name = 'unityCatalog'
  AND action_name IN ('UpdateTagSubentityAssignments', 'createEntityTagAssignment', 'deleteEntityTagAssignment')
  AND to_json(request_params) LIKE '%class.%'
  AND request_params.securable_full_name RLIKE '^rtr_demo_catalog\\.(ehr_bronze|clinical_silver|care_management_silver|readmission_worklist_gold|readmission_worklist_app_bronze)\\.'
ORDER BY event_time
-- ### C3: principal 77f19abf-81ef-4969-ad97-cc0e63a8f662 (is it a person or a service principal?)
SELECT DISTINCT user_identity.email AS principal, identity_metadata.run_by, identity_metadata.run_as, user_agent
FROM system.access.audit
WHERE event_date BETWEEN '2026-11-04' AND '2026-11-04' AND user_identity.email = '77f19abf-81ef-4969-ad97-cc0e63a8f662'
  AND action_name = 'UpdateTagSubentityAssignments'
-- ### C3: who made those calls, by action (summary)
SELECT action_name, user_identity.email, count(*) n, min(event_time) first_event, max(event_time) last_event
FROM system.access.audit
WHERE event_date BETWEEN '2026-11-03' AND '2026-11-09' AND service_name = 'unityCatalog'
  AND action_name IN ('UpdateTagSubentityAssignments', 'createEntityTagAssignment', 'deleteEntityTagAssignment')
  AND to_json(request_params) LIKE '%class.%'
  AND request_params.securable_full_name RLIKE '^rtr_demo_catalog\\.(ehr_bronze|clinical_silver|care_management_silver|readmission_worklist_gold|readmission_worklist_app_bronze)\\.'
GROUP BY 1, 2 ORDER BY 4
-- ### C4: leadership test functions for the author, a member of workspace-local group care_mgmt_leadership
SELECT current_user() AS user, is_member('care_mgmt_leadership') AS is_member, is_account_group_member('care_mgmt_leadership') AS is_account_group_member
-- ### C4: the facility filter function's leadership branch for the author (all facilities)
SELECT count(*) facilities_visible_through_filter FROM rtr_demo_catalog.clinical_silver.facility f
WHERE rtr_demo_catalog.phi_governance.filter_by_facility(f.facility_id)
-- ### C5: care_team_assignment profile (why the assigned-subset branch is untested, #67)
SELECT count(DISTINCT care_manager_email) care_managers, count(*) rows,
       count_if(expiration_date IS NULL OR expiration_date > current_date()) active_rows,
       count(DISTINCT facility_id) facilities, collect_set(facility_id) facility_ids
FROM rtr_demo_catalog.care_management_silver.care_team_assignment
-- ### C5: event_log tables that stay in readmission_worklist_gold (#48 correction, #67)
SELECT table_name, table_type, created, last_altered
FROM rtr_demo_catalog.information_schema.tables
WHERE table_schema = 'readmission_worklist_gold' AND table_name LIKE 'event_log_%' ORDER BY 1
-- ### C3: care_worklist_synced was recreated after the 2026-11-06 12:54 tag (#48), so that class.name tag went with the old table
SELECT table_name, table_type, created, created_by FROM rtr_demo_catalog.information_schema.tables
WHERE table_schema = 'readmission_worklist_gold' AND table_name IN ('care_worklist_synced', 'care_team_roster_synced', 'care_worklist')
-- ### C3: tags on care_worklist_synced columns now (expected: phi_data_classification and row_filter_policy from #66, no class.*)
SELECT column_name, tag_name, tag_value FROM rtr_demo_catalog.information_schema.column_tags
WHERE schema_name = 'readmission_worklist_gold' AND table_name = 'care_worklist_synced' ORDER BY 1, 2
