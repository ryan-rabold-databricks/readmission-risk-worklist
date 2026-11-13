# Server-side confirmation of the #54 app checks in app_checks_console.txt: the deployed app's request logs
# (app_otel_logs, exported by Databricks Apps telemetry), its audit events, and what the writes did (CDF history).
# Client IP and user agent redacted; IDs only.
-- ### Request log lines 2026-11-13 15:00-15:20 UTC for the routes the checks called
SELECT time,
       regexp_extract(CAST(body AS STRING), '"((GET|POST) /api/[^ ?"]*)', 1) request,
       regexp_extract(CAST(body AS STRING), 'HTTP/[0-9.]+" ([0-9]{3})', 1) status
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
WHERE time BETWEEN TIMESTAMP'2026-11-13T15:00:00Z' AND TIMESTAMP'2026-11-13T15:20:00Z'
  AND CAST(body AS STRING) RLIKE '"(GET|POST) /api/(worklist/items|settings/changes|me)'
ORDER BY time
-- ### Audit events in the same window (one outreach.logged for the 201, none for the 400, 404, retry, or 403s)
SELECT time, attributes:['event.name']::string event, attributes:['audit.action']::string action,
       attributes:['audit.record_type']::string record_type, attributes:['audit.record_id']::string record_id,
       attributes:['audit.facility_id']::string facility_id
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
WHERE instrumentation_scope.name = 'readmission-worklist.audit'
  AND time BETWEEN TIMESTAMP'2026-11-13T15:00:00Z' AND TIMESTAMP'2026-11-13T15:20:00Z'
ORDER BY time
-- ### Writes as landed by Lakebase CDF: exactly one row for the retried client_request_id, none for item B
SELECT 'retried client_request_id c10cdb54-...' check, count(*) rows, count(DISTINCT activity_id) activity_ids,
       max(activity_type) activity_type, max(worklist_item_id) worklist_item_id
FROM rtr_demo_catalog.readmission_worklist_app_bronze.lb_outreach_activity_history
WHERE client_request_id = 'c10cdb54-cbeb-40c3-aa70-2200a1be92b5'
UNION ALL
SELECT 'rows for item B (out of scope) written on 2026-11-13 (expect 0; its 2026-10 simulator history is not counted)', count(*), count(DISTINCT activity_id), max(activity_type), max(worklist_item_id)
FROM rtr_demo_catalog.readmission_worklist_app_bronze.lb_outreach_activity_history
WHERE worklist_item_id = '004e03c77413df74e837e386b1e1a59e33c278c71a0dc35f07fc12d8f6b5c47d'
  AND (activity_ts >= TIMESTAMP'2026-11-13T00:00:00Z' OR created_at >= TIMESTAMP'2026-11-13T00:00:00Z')
UNION ALL
SELECT 'rows for item A written 2026-11-13 15:00-15:20 (only the check 3 row expected)', count(*), count(DISTINCT activity_id), max(activity_type), max(worklist_item_id)
FROM rtr_demo_catalog.readmission_worklist_app_bronze.lb_outreach_activity_history
WHERE worklist_item_id = 'b3a1642ccb141970835fb7cc9950931205245c72a34d4606001512fbbeb8e302'
  AND activity_ts BETWEEN TIMESTAMP'2026-11-13T15:00:00Z' AND TIMESTAMP'2026-11-13T15:20:00Z'
-- ### No settings change was written during the non-leader check
SELECT count(*) settings_changes_2026_11_13
FROM rtr_demo_catalog.readmission_worklist_app_bronze.lb_program_setting_change_history
WHERE changed_at >= TIMESTAMP'2026-11-13T00:00:00Z'
