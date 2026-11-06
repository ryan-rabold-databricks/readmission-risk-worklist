// Worklist tab API. Reads the synced worklist and roster (read-only) and appends outreach
// activity, all through the app service principal's Lakebase pool. UC row filters do not
// reach Postgres, so every query is scoped to the facilities the signed-in user is
// rostered at for the worklist day (care_team_roster_synced).

import type { Application, Request, Response } from 'express';
import { z } from 'zod';
import { emitAudit } from '../audit';
import { APP_SCHEMA, SYNCED_SCHEMA } from '../config';
import { userEmail } from '../identity';
import type { LakebaseQuery } from './types';
import { handle } from './types';

export const ACTIVITY_TYPES = ['NO_ANSWER', 'LEFT_VOICEMAIL', 'REACHED', 'FOLLOWUP_BOOKED', 'DECLINED', 'UNREACHABLE'] as const;
const CONTACT_TYPES = ['REACHED', 'FOLLOWUP_BOOKED', 'DECLINED'];
const NOTE_MAX = 1000;
const NEXT_STEP_MAX_DAYS = 30;

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const OutreachBody = z.object({
  client_request_id: z.string().uuid(),
  activity_type: z.enum(ACTIVITY_TYPES),
  next_step_due_at: z.string().datetime({ offset: true }).nullable().optional(),
  note: z.string().trim().max(NOTE_MAX).nullable().optional(),
});

// Item columns plus a per-item outreach summary. The facility join to the roster is the
// access scope: a user sees only facilities they work that day.
const ITEM_SELECT = `
  w.worklist_item_id, w.facility_id, w.worklist_date::text AS worklist_date, w.assignment_status,
  w.assigned_care_manager, w.patient_display_name, w.phone, w.risk_score, w.risk_tier, w.top_drivers,
  w.outreach_brief, w.due_at, w.created_at,
  coalesce(a.attempts, 0)::int AS attempts, a.last_activity_type, a.last_activity_ts, a.next_step_due_at,
  coalesce(a.reached, false) AS reached`;
const ITEM_FROM = `
  ${SYNCED_SCHEMA}.care_worklist_synced w
  JOIN ${SYNCED_SCHEMA}.care_team_roster_synced r
    ON r.facility_id = w.facility_id AND r.roster_date = w.worklist_date AND r.care_manager_email = $1
  LEFT JOIN LATERAL (
    SELECT count(*) AS attempts,
           (array_agg(o.activity_type ORDER BY o.activity_ts DESC, o.created_at DESC))[1] AS last_activity_type,
           max(o.activity_ts) AS last_activity_ts,
           (array_agg(o.next_step_due_at ORDER BY o.activity_ts DESC, o.created_at DESC))[1] AS next_step_due_at,
           bool_or(o.activity_type IN (${CONTACT_TYPES.map((t) => `'${t}'`).join(', ')})) AS reached
    FROM ${APP_SCHEMA}.outreach_activity o
    WHERE o.worklist_item_id = w.worklist_item_id
  ) a ON true`;

export function registerWorklistRoutes(app: Application, db: LakebaseQuery) {
  // Worklist days the user can see, newest first (the synced window is 30 days).
  app.get('/api/worklist/dates', handle(async (req: Request, res: Response) => {
    const email = userEmail(req);
    const { rows } = await db.query(
      `SELECT DISTINCT roster_date::text AS worklist_date FROM ${SYNCED_SCHEMA}.care_team_roster_synced
       WHERE care_manager_email = $1 ORDER BY 1 DESC`,
      [email],
    );
    res.json(rows.map((r) => r.worklist_date));
  }));

  app.get('/api/worklist', handle(async (req: Request, res: Response) => {
    const email = userEmail(req);
    const date = isoDate.safeParse(req.query.date);
    if (!date.success) {
      res.status(400).json({ error: 'date (YYYY-MM-DD) is required' });
      return;
    }
    const { rows } = await db.query(
      `SELECT ${ITEM_SELECT} FROM ${ITEM_FROM} WHERE w.worklist_date = $2::date ORDER BY w.risk_score DESC, w.worklist_item_id`,
      [email, date.data],
    );
    emitAudit({ name: 'worklist.viewed', userEmail: email, action: 'list', recordType: 'worklist_day', recordId: date.data, count: rows.length });
    res.json(rows);
  }));

  app.get('/api/worklist/items/:id', handle(async (req: Request, res: Response) => {
    const email = userEmail(req);
    const { rows } = await db.query(`SELECT ${ITEM_SELECT} FROM ${ITEM_FROM} WHERE w.worklist_item_id = $2`, [email, req.params.id]);
    if (!rows.length) {
      res.status(404).json({ error: 'Worklist item not found' });
      return;
    }
    const history = await db.query(
      `SELECT activity_id::text AS activity_id, care_manager_email, activity_type, activity_ts, next_step_due_at, note
       FROM ${APP_SCHEMA}.outreach_activity WHERE worklist_item_id = $1 ORDER BY activity_ts DESC, created_at DESC`,
      [req.params.id],
    );
    const item = rows[0];
    emitAudit({ name: 'worklist.viewed', userEmail: email, action: 'open', recordType: 'worklist_item', recordId: String(item.worklist_item_id), facilityId: String(item.facility_id) });
    res.json({ item, history: history.rows });
  }));

  // Append one outreach activity. Idempotent on client_request_id: a retried request
  // returns the row the first attempt created.
  app.post('/api/worklist/items/:id/outreach', handle(async (req: Request, res: Response) => {
    const email = userEmail(req);
    const body = OutreachBody.safeParse(req.body);
    if (!body.success) {
      res.status(400).json({ error: 'Invalid outreach', issues: body.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`) });
      return;
    }
    const { client_request_id, activity_type, next_step_due_at, note } = body.data;
    if (next_step_due_at) {
      const due = Date.parse(next_step_due_at);
      if (due <= Date.now() || due > Date.now() + NEXT_STEP_MAX_DAYS * 86_400_000) {
        res.status(400).json({ error: `next_step_due_at must be in the next ${NEXT_STEP_MAX_DAYS} days` });
        return;
      }
    }
    const scope = await db.query(`SELECT w.facility_id FROM ${ITEM_FROM} WHERE w.worklist_item_id = $2`, [email, req.params.id]);
    if (!scope.rows.length) {
      res.status(404).json({ error: 'Worklist item not found' });
      return;
    }
    const inserted = await db.query(
      `INSERT INTO ${APP_SCHEMA}.outreach_activity
         (worklist_item_id, client_request_id, care_manager_email, activity_type, activity_ts, next_step_due_at, note)
       VALUES ($1, $2, $3, $4, now(), $5, $6)
       ON CONFLICT (client_request_id) DO NOTHING
       RETURNING activity_id::text AS activity_id, activity_type, activity_ts, next_step_due_at, note, care_manager_email`,
      [req.params.id, client_request_id, email, activity_type, next_step_due_at ?? null, note || null],
    );
    if (!inserted.rows.length) {
      const existing = await db.query(
        `SELECT activity_id::text AS activity_id, activity_type, activity_ts, next_step_due_at, note, care_manager_email, worklist_item_id
         FROM ${APP_SCHEMA}.outreach_activity WHERE client_request_id = $1`,
        [client_request_id],
      );
      if (existing.rows[0]?.worklist_item_id !== req.params.id) {
        res.status(409).json({ error: 'client_request_id already used for another item' });
        return;
      }
      res.status(200).json(existing.rows[0]);
      return;
    }
    const row = inserted.rows[0];
    emitAudit({ name: 'outreach.logged', userEmail: email, action: activity_type, recordType: 'outreach_activity', recordId: String(row.activity_id), facilityId: String(scope.rows[0].facility_id) });
    res.status(201).json(row);
  }));
}
