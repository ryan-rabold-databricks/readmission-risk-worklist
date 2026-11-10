# C10: app access-scope responses from the 2026-11-07 Phase 5 validation (#54), from the app's own request
# logs in app_otel_logs (stdout exported by Databricks Apps telemetry, #55). IDs and paths only.
# B6: attributes of every audit.genie.asked record, to resolve the None values in
# evidence/phase6/genie_in_app_after_resignin.txt.
-- ### C10: request log line format (one example; client IP and user agent redacted)
SELECT time, regexp_replace(regexp_replace(CAST(body AS STRING), '^[0-9a-f.:]+ ', '<client-ip> '), '"Mozilla[^"]*"', '"<user-agent>"') body
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
WHERE CAST(body AS STRING) RLIKE '"(GET|POST) /api/' LIMIT 1
-- ### C10: app API responses on 2026-11-07 by method, route, and status
WITH r AS (
  SELECT time, regexp_extract(CAST(body AS STRING), '"(GET|POST|PUT|DELETE) (/api/[^ ?"]*)', 1) method,
         regexp_extract(CAST(body AS STRING), '"(GET|POST|PUT|DELETE) (/api/[^ ?"]*)', 2) path,
         regexp_extract(CAST(body AS STRING), 'HTTP/[0-9.]+" ([0-9]{3})', 1) status
  FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
  WHERE date = '2026-11-07' AND CAST(body AS STRING) RLIKE '"(GET|POST|PUT|DELETE) /api/'
)
SELECT method, regexp_replace(path, '/[0-9a-f]{32,}|/[0-9a-f-]{36}', '/<id>') route, status, count(*) n, min(time) first_seen, max(time) last_seen
FROM r GROUP BY 1, 2, 3 ORDER BY 2, 1, 3
-- ### C10: the non-2xx responses in time order (out-of-roster 404, invalid activity 400, pre-group 403)
SELECT time, regexp_extract(CAST(body AS STRING), '"((GET|POST|PUT|DELETE) /api/[^"]*)"', 1) request_line,
       regexp_extract(CAST(body AS STRING), 'HTTP/[0-9.]+" ([0-9]{3})', 1) status
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
WHERE CAST(body AS STRING) RLIKE '"(GET|POST|PUT|DELETE) /api/' AND regexp_extract(CAST(body AS STRING), 'HTTP/[0-9.]+" ([0-9]{3})', 1) NOT LIKE '2%'
ORDER BY time
-- ### C10: outreach writes on 2026-11-07 (201 created, 200 idempotent retry)
SELECT time, regexp_extract(CAST(body AS STRING), '"((GET|POST|PUT|DELETE) /api/[^"]*)"', 1) request_line,
       regexp_extract(CAST(body AS STRING), 'HTTP/[0-9.]+" ([0-9]{3})', 1) status
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
WHERE date = '2026-11-07' AND CAST(body AS STRING) RLIKE '"POST /api/'
ORDER BY time
-- ### B6: every audit.genie.asked record (the event name is in attributes['event.name'] and the body; the top-level event_name column is empty for these records, which is why phase6/genie_in_app_after_resignin.txt shows None)
SELECT time, event_name AS top_level_event_name, attributes:['event.name']::string AS attr_event_name, CAST(body AS STRING) body,
       attributes:['audit.action']::string AS action, attributes:['audit.record_type']::string AS record_type,
       attributes:['audit.record_id']::string AS record_id, attributes:['audit.user_email']::string AS user_email
FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
WHERE instrumentation_scope.name = 'readmission-worklist.audit' AND attributes:['event.name']::string = 'audit.genie.asked' ORDER BY time
-- ### B6: audit records in bronze vs curated silver app_audit_event, by event (silver lags until the next pipeline run)
SELECT b.event, b.bronze_records, s.silver_rows, b.latest_bronze, s.latest_silver FROM
 (SELECT attributes:['event.name']::string event, count(*) bronze_records, max(time) latest_bronze
  FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs WHERE instrumentation_scope.name = 'readmission-worklist.audit' GROUP BY 1) b
FULL OUTER JOIN
 (SELECT CASE WHEN event_name LIKE 'audit.%' THEN event_name ELSE concat('audit.', event_name) END event, count(*) silver_rows, max(event_ts) latest_silver
  FROM rtr_demo_catalog.care_management_silver.app_audit_event GROUP BY 1) s USING (event)
ORDER BY 1
-- ### C10: any 4xx response from the deployed app in the whole telemetry window (2026-11-06 22:57 onward)
SELECT count(*) responses_4xx FROM rtr_demo_catalog.readmission_worklist_app_bronze.app_otel_logs
WHERE CAST(body AS STRING) RLIKE 'HTTP/[0-9.]+" 4[0-9]{2}'
