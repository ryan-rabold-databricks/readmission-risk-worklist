# C1: PHI content checks re-run against real names (DECISIONS.md #31, #55)
# Replaces two checks that ran while catalog auto-classification had written "REDACTED"
# into patient names (2026-11-04 to 2026-11-08, #60), so they compared against "REDACTED":
#   evidence/phase3/worklist_validation.md   (brief check, run 2026-11-05)
#   evidence/phase5/audit_event_validation.raw.txt (telemetry PHI scan, run 2026-11-07)
# Run as the pipeline identity, which the ABAC masks exempt (#62), so it reads real values.
-- ### Precondition: names in the sources are real (not REDACTED, not masked)
SELECT
  (SELECT count(*) FROM rtr_demo_catalog.clinical_silver.patient) silver_patients,
  (SELECT count_if(first_name IN ('REDACTED', '***') OR last_name IN ('REDACTED', '***')) FROM rtr_demo_catalog.clinical_silver.patient) silver_redacted_or_masked,
  (SELECT count(DISTINCT last_name) FROM rtr_demo_catalog.clinical_silver.patient) silver_distinct_last_names,
  (SELECT count(*) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist) worklist_items,
  (SELECT count_if(patient_display_name LIKE '%REDACTED%' OR patient_display_name LIKE '%***%') FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist) worklist_redacted_or_masked,
  (SELECT count(DISTINCT patient_display_name) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist) worklist_distinct_names
-- ### Briefs: does any stored brief contain the patient's own first name, last name, MRN, or phone digits?
WITH b AS (
  SELECT w.worklist_item_id, w.outreach_brief, w.phone, p.first_name, p.last_name, p.mrn
  FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist w
  JOIN rtr_demo_catalog.clinical_silver.patient p USING (patient_id)
  WHERE length(trim(w.outreach_brief)) >= 80
)
SELECT
  count(*) briefs,
  count_if(outreach_brief RLIKE concat('(?i)\\b', first_name, '\\b')) contains_first_name,
  count_if(outreach_brief RLIKE concat('(?i)\\b', last_name, '\\b')) contains_last_name,
  count_if(instr(outreach_brief, mrn) > 0) contains_mrn,
  count_if(phone IS NOT NULL AND instr(regexp_replace(outreach_brief, '[^0-9]', ''), regexp_replace(phone, '[^0-9]', '')) > 0) contains_phone_digits,
  count_if(outreach_brief RLIKE '\\(?[0-9]{3}\\)?[-. ][0-9]{3}[-. ][0-9]{4}') contains_any_phone_pattern
FROM b
-- ### Briefs: does any brief contain ANY patient's full name (not just its own)?
SELECT count(*) briefs_with_any_worklist_full_name
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist w
WHERE length(trim(w.outreach_brief)) >= 80
  AND EXISTS (SELECT 1 FROM (SELECT DISTINCT patient_display_name n FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist) x
              WHERE instr(lower(w.outreach_brief), lower(x.n)) > 0)
-- ### Telemetry: app_otel_logs records scanned
SELECT count(*) records, min(time) first_record, max(time) last_record,
       count_if(instrumentation_scope.name = 'readmission-worklist.audit') audit_records
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
-- ### Telemetry: records containing any worklist patient full name, last name (word match), MRN, or phone
WITH logs AS (
  SELECT record_id, lower(concat_ws(' ', to_json(body), to_json(attributes))) txt,
         regexp_replace(concat_ws(' ', to_json(body), to_json(attributes)), '[^0-9]', ' ') digits
  FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
),
pts AS (
  SELECT DISTINCT lower(p.first_name) fn, lower(p.last_name) ln, p.mrn, regexp_replace(w.phone, '[^0-9]', '') ph
  FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist w
  JOIN rtr_demo_catalog.clinical_silver.patient p USING (patient_id)
)
SELECT
  (SELECT count(DISTINCT l.record_id) FROM logs l JOIN pts ON instr(l.txt, concat(pts.fn, ' ', pts.ln)) > 0) full_name_hits,
  (SELECT count(DISTINCT l.record_id) FROM logs l JOIN (SELECT DISTINCT ln FROM pts) p ON l.txt RLIKE concat('\\b', p.ln, '\\b')) last_name_word_hits,
  (SELECT count(DISTINCT l.record_id) FROM logs l JOIN (SELECT DISTINCT mrn FROM pts) p ON instr(l.txt, lower(p.mrn)) > 0) mrn_hits,
  (SELECT count(DISTINCT l.record_id) FROM logs l JOIN (SELECT DISTINCT ph FROM pts WHERE ph <> '') p ON instr(regexp_replace(l.digits, ' ', ''), p.ph) > 0) phone_digit_hits,
  (SELECT count(*) FROM logs WHERE txt RLIKE '\\(?[0-9]{3}\\)?[-. ][0-9]{3}[-. ][0-9]{4}') phone_pattern_hits,
  (SELECT count(*) FROM logs WHERE txt RLIKE '\\bselect\\b.+\\bfrom\\b') sql_text_hits
-- ### Telemetry: if any last-name word hits, show which words (IDs and the matched word only)
WITH logs AS (
  SELECT record_id, lower(concat_ws(' ', to_json(body), to_json(attributes))) txt
  FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
),
lns AS (SELECT DISTINCT lower(p.last_name) ln FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist w JOIN rtr_demo_catalog.clinical_silver.patient p USING (patient_id))
SELECT lns.ln matched_word, count(DISTINCT l.record_id) records
FROM logs l JOIN lns ON l.txt RLIKE concat('\\b', lns.ln, '\\b')
GROUP BY 1 ORDER BY 2 DESC LIMIT 20
-- ### Positive control: the same name and phone matching finds each patient in their own worklist row (expect all rows)
SELECT count(*) worklist_rows,
       count_if(w.patient_display_name RLIKE concat('(?i)\\b', p.last_name, '\\b')) last_name_regex_matches,
       count_if(instr(lower(w.patient_display_name), lower(concat(p.first_name, ' ', p.last_name))) > 0) full_name_matches
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist w
JOIN rtr_demo_catalog.clinical_silver.patient p USING (patient_id)
-- ### Positive control: the telemetry scan reads body and attributes (the signed-in user's email appears in audit attributes)
SELECT count_if(lower(concat_ws(' ', to_json(body), to_json(attributes))) LIKE '%ryan.rabold@databricks.com%') records_with_user_email,
       count_if(lower(to_json(attributes)) LIKE '%audit.%') records_with_audit_attributes
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
