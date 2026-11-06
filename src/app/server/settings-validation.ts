// Program Settings change validation. Mirrors readmit.pipeline.program_settings (the
// pipeline re-validates every change; DECISIONS.md #51), so a change the app accepts is
// one the pipeline will apply. Keep the two in sync.

import { z } from 'zod';

export const SETTING_TYPES = ['RISK_TIER_POLICY', 'CARE_TEAM_ASSIGNMENT', 'CARE_MANAGER_CAPACITY'] as const;
export const TIERS_LOW_TO_HIGH = ['LOW', 'MEDIUM', 'HIGH'] as const;
export const MAX_DAILY_CAPACITY = 500;
export const MAX_SLA_HOURS = 24 * 14;

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'must be YYYY-MM-DD');
const email = z.string().email().refine((e) => e === e.toLowerCase(), 'must be lowercase');

const tier = z.object({
  risk_tier: z.enum(TIERS_LOW_TO_HIGH),
  min_score: z.number().min(0).max(1),
  max_score: z.number().min(0).max(1),
  outreach_sla_hours: z.number().int().min(1).max(MAX_SLA_HOURS),
  include_in_worklist: z.boolean(),
});

export const SettingChangeBody = z.discriminatedUnion('setting_type', [
  z.object({
    setting_type: z.literal('RISK_TIER_POLICY'),
    target_key: z.literal('ALL'),
    new_value: z.object({ tiers: z.array(tier).length(3) }),
    change_reason: z.string().trim().min(5).max(500),
    effective_date: isoDate,
    client_request_id: z.string().uuid(),
  }),
  z.object({
    setting_type: z.literal('CARE_TEAM_ASSIGNMENT'),
    target_key: email,
    new_value: z.object({ facility_ids: z.array(z.string().min(1)) }),
    change_reason: z.string().trim().min(5).max(500),
    effective_date: isoDate,
    client_request_id: z.string().uuid(),
  }),
  z.object({
    setting_type: z.literal('CARE_MANAGER_CAPACITY'),
    target_key: email,
    new_value: z.object({ daily_capacity: z.number().int().min(1).max(MAX_DAILY_CAPACITY) }),
    change_reason: z.string().trim().min(5).max(500),
    effective_date: isoDate,
    client_request_id: z.string().uuid(),
  }),
]);
export type SettingChange = z.infer<typeof SettingChangeBody>;

/** Rules zod cannot express: tier contiguity, known facilities, no retroactive dates.
 * Returns the problems found (empty = valid). `today` is the UTC date the change is made. */
export function settingProblems(change: SettingChange, today: string, facilities: Set<string>): string[] {
  const problems: string[] = [];
  if (change.effective_date < today) problems.push('effective_date is before the change was made');
  if (change.setting_type === 'RISK_TIER_POLICY') {
    const byTier = new Map(change.new_value.tiers.map((t) => [t.risk_tier, t]));
    if (byTier.size !== 3) return [...problems, 'tiers must list HIGH, MEDIUM, and LOW exactly once'];
    const ordered = TIERS_LOW_TO_HIGH.map((n) => byTier.get(n)!);
    for (const t of ordered) {
      if (!(t.min_score < t.max_score)) problems.push(`${t.risk_tier}: min_score must be below max_score`);
    }
    if (ordered[0].min_score !== 0 || ordered[2].max_score !== 1) problems.push('tiers must cover scores from 0 to 1');
    for (let i = 0; i < 2; i++) {
      if (ordered[i].max_score !== ordered[i + 1].min_score) {
        problems.push(`${ordered[i].risk_tier} max_score must equal ${ordered[i + 1].risk_tier} min_score`);
      }
    }
  }
  if (change.setting_type === 'CARE_TEAM_ASSIGNMENT') {
    const unknown = change.new_value.facility_ids.filter((f) => !facilities.has(f));
    if (unknown.length) problems.push(`unknown facility_ids: ${unknown.join(', ')}`);
  }
  return problems;
}
