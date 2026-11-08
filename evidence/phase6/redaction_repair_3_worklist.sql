-- One-time data repair (DECISIONS.md #60): restore patient_display_name in care_worklist,
-- written as 'REDACTED REDACTED' while a catalog-level mask applied to the job identity.
-- Idempotent: only rows whose name differs from silver are touched; nothing else changes.
MERGE INTO rtr_demo_catalog.readmission_worklist_gold.care_worklist t
USING (SELECT patient_id, concat_ws(' ', first_name, last_name) AS display_name
       FROM rtr_demo_catalog.clinical_silver.patient) p
ON t.patient_id = p.patient_id AND t.patient_display_name <> p.display_name
WHEN MATCHED THEN UPDATE SET
  t.patient_display_name = p.display_name,
  t.audit_updated_at = current_timestamp(),
  t.audit_updated_by = current_user(),
  t.audit_updated_process = 'redaction_repair',
  t.audit_updated_run_id = 'redaction_repair:2026-11-08'
