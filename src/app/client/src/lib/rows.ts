// Analytics (warehouse) results arrive over the JSON_ARRAY wire format with every value as
// a string ("0.14", "false", '["FAC-A"]'), although the generated query types say
// number / boolean / array. Parse each result through a schema that coerces the values.

import { z } from 'zod';

const num = z
  .union([z.number(), z.string()])
  .nullable()
  .transform((v) => (v === null ? null : Number(v)));
const reqNum = z.union([z.number(), z.string()]).transform(Number);
const bool = z.union([z.boolean(), z.string()]).transform((v) => v === true || v === 'true');
const str = z.string();
const optStr = z.string().nullable();
const strArray = z.union([z.array(z.string()), z.string()]).transform((v) => (Array.isArray(v) ? v : z.array(z.string()).parse(JSON.parse(v))));

export const ProgramKpis = z.object({
  program_start: str,
  matured_through: str,
  data_through: str,
  latest_worklist_date: str,
  program_discharges: reqNum,
  program_readmit_rate: num,
  baseline_readmit_rate: num,
  program_followup_7d_rate: num,
  baseline_followup_7d_rate: num,
  reach_rate: num,
  worklist_items: reqNum,
  overflow_items: reqNum,
  median_first_contact_hours: num,
  readmissions_avoided: reqNum,
  est_cost_avoided: reqNum,
  matured_program_discharges: reqNum,
  readmissions_avoided_yoy: reqNum,
  est_cost_avoided_yoy: reqNum,
});

export const FacilityRow = z.object({
  facility_id: str,
  facility_name: str,
  program_discharges: reqNum,
  program_readmit_rate: num,
  baseline_readmit_rate: num,
  program_followup_7d_rate: num,
  reach_rate: num,
  overflow_items: reqNum,
});

export const TierEffectRow = z.object({
  risk_tier: str,
  outreach_group: str,
  items: reqNum,
  readmit_rate: num,
  followup_7d_rate: num,
  mean_predicted_risk: num,
});

export const PolicyRow = z.object({
  risk_tier: str,
  min_score: reqNum,
  max_score: reqNum,
  outreach_sla_hours: reqNum,
  include_in_worklist: bool,
  effective_date: str,
  expiration_date: optStr,
  set_by: str,
  source: str,
});

export const CareTeamRow = z.object({
  care_manager_email: str,
  facility_ids: strArray,
  daily_capacity: num,
});

export const ChangeStatusRow = z.object({
  change_id: str,
  status: str,
  status_reason: optStr,
});

export const FacilityOption = z.object({ facility_id: str, facility_name: str });

/** Coerce a query result. rows is null while loading; a row that does not match the
 * schema becomes the view's error instead of a silently wrong number. */
export function coerce<S extends z.ZodTypeAny>(
  schema: S,
  q: { data: unknown; loading: boolean; error: string | null },
): { rows: z.infer<S>[] | null; loading: boolean; error: string | null } {
  if (q.error || q.data === null || q.data === undefined) return { rows: null, loading: q.loading, error: q.error };
  const parsed = z.array(schema).safeParse(q.data);
  return parsed.success
    ? { rows: parsed.data, loading: q.loading, error: null }
    : { rows: null, loading: false, error: `Unexpected query result: ${parsed.error.issues[0]?.message ?? 'invalid'}` };
}
