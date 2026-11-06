// Business audit events (DECISIONS.md #12, #13) as OpenTelemetry log records.
//
// AppKit registers a global OTLP LoggerProvider when the platform injects
// OTEL_EXPORTER_OTLP_ENDPOINT (app telemetry enabled in the bundle), so these records land
// in readmission_worklist_app_bronze.app_otel_logs. The pipeline curates them into
// care_management_silver.app_audit_event, de-duplicated on event_id.
//
// IDs only, never PHI: no patient names, phones, notes, or briefs in any attribute.

import { randomUUID } from 'node:crypto';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';

export type AuditEventName = 'worklist.viewed' | 'outreach.logged' | 'settings.changed' | 'genie.asked';

export interface AuditEvent {
  name: AuditEventName;
  userEmail: string;
  action: string;
  recordType?: string;
  recordId?: string;
  facilityId?: string;
  count?: number;
}

const logger = logs.getLogger('readmission-worklist.audit');

export function emitAudit(event: AuditEvent): string {
  const eventId = randomUUID();
  const attributes: Record<string, string | number> = {
    'event.name': `audit.${event.name}`,
    'audit.event_id': eventId,
    'audit.user_email': event.userEmail,
    'audit.action': event.action,
  };
  if (event.recordType) attributes['audit.record_type'] = event.recordType;
  if (event.recordId) attributes['audit.record_id'] = event.recordId;
  if (event.facilityId) attributes['audit.facility_id'] = event.facilityId;
  if (event.count !== undefined) attributes['audit.count'] = event.count;
  logger.emit({ severityNumber: SeverityNumber.INFO, severityText: 'INFO', body: `audit.${event.name}`, attributes });
  return eventId;
}
