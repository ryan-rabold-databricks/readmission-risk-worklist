// Program Settings tab API (care_mgmt_leadership only). Changes are appended to Lakebase
// readmission_worklist_app.program_setting_change; Lakebase CDF lands them in the
// lakehouse and the next pipeline update validates and applies them (DECISIONS.md #51).
// Current, applied settings are read by the client from Unity Catalog (OBO queries).

import type { Application, Request, Response } from 'express';
import { emitAudit } from '../audit';
import { APP_SCHEMA, SYNCED_SCHEMA } from '../config';
import { isLeader, userEmail } from '../identity';
import { SettingChangeBody, settingProblems } from '../settings-validation';
import type { LakebaseQuery } from './types';
import { handle } from './types';

async function requireLeader(req: Request, res: Response): Promise<string | null> {
  const email = userEmail(req);
  if (!(await isLeader(email))) {
    res.status(403).json({ error: 'Program Settings is limited to care management leadership' });
    return null;
  }
  return email;
}

export function registerSettingsRoutes(app: Application, db: LakebaseQuery) {
  app.get('/api/settings/changes', handle(async (req: Request, res: Response) => {
    if (!(await requireLeader(req, res))) return;
    const { rows } = await db.query(
      `SELECT change_id::text AS change_id, setting_type, target_key, new_value_json, change_reason,
              effective_date::text AS effective_date, changed_by, changed_at
       FROM ${APP_SCHEMA}.program_setting_change ORDER BY changed_at DESC, change_id LIMIT 100`,
    );
    res.json(rows);
  }));

  app.post('/api/settings/changes', handle(async (req: Request, res: Response) => {
    const email = await requireLeader(req, res);
    if (!email) return;
    const body = SettingChangeBody.safeParse(req.body);
    if (!body.success) {
      res.status(400).json({ error: 'Invalid change', issues: body.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`) });
      return;
    }
    // Facilities the app knows about: everything on the synced worklist or roster. The
    // pipeline re-checks against clinical_silver.facility.
    const known = await db.query(
      `SELECT facility_id FROM ${SYNCED_SCHEMA}.care_worklist_synced
       UNION SELECT facility_id FROM ${SYNCED_SCHEMA}.care_team_roster_synced`,
    );
    const today = new Date().toISOString().slice(0, 10);
    const problems = settingProblems(body.data, today, new Set(known.rows.map((r) => String(r.facility_id))));
    if (problems.length) {
      res.status(400).json({ error: 'Invalid change', issues: problems });
      return;
    }
    const c = body.data;
    const inserted = await db.query(
      `INSERT INTO ${APP_SCHEMA}.program_setting_change
         (client_request_id, setting_type, target_key, new_value_json, change_reason, effective_date, changed_by)
       VALUES ($1, $2, $3, $4::jsonb, $5, $6::date, $7)
       ON CONFLICT (client_request_id) DO NOTHING
       RETURNING change_id::text AS change_id, changed_at`,
      [c.client_request_id, c.setting_type, c.target_key, JSON.stringify(c.new_value), c.change_reason, c.effective_date, email],
    );
    if (!inserted.rows.length) {
      const existing = await db.query(
        `SELECT change_id::text AS change_id, changed_at FROM ${APP_SCHEMA}.program_setting_change WHERE client_request_id = $1`,
        [c.client_request_id],
      );
      res.status(200).json(existing.rows[0]);
      return;
    }
    emitAudit({ name: 'settings.changed', userEmail: email, action: c.setting_type, recordType: 'program_setting_change', recordId: String(inserted.rows[0].change_id) });
    res.status(201).json(inserted.rows[0]);
  }));
}
