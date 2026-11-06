import { describe, expect, it } from 'vitest';
import { SettingChangeBody, settingProblems } from './settings-validation';

const FACILITIES = new Set(['FAC-A', 'FAC-B']);
const TODAY = '2026-11-07';
const ID = '6f1c1f0e-7d5b-4a51-9a51-0c2f6a3b1e11';

function tiers(highMin = 0.3, medMin = 0.18) {
  return [
    { risk_tier: 'HIGH', min_score: highMin, max_score: 1, outreach_sla_hours: 24, include_in_worklist: true },
    { risk_tier: 'MEDIUM', min_score: medMin, max_score: highMin, outreach_sla_hours: 72, include_in_worklist: true },
    { risk_tier: 'LOW', min_score: 0, max_score: medMin, outreach_sla_hours: 168, include_in_worklist: false },
  ];
}

function parse(body: object) {
  return SettingChangeBody.parse({ change_reason: 'Testing a change', effective_date: '2026-11-10', client_request_id: ID, ...body });
}

describe('settingProblems', () => {
  it('accepts a contiguous tier policy', () => {
    const c = parse({ setting_type: 'RISK_TIER_POLICY', target_key: 'ALL', new_value: { tiers: tiers(0.35) } });
    expect(settingProblems(c, TODAY, FACILITIES)).toEqual([]);
  });

  it('rejects a gap between tiers', () => {
    const t = tiers();
    t[1].max_score = 0.29;
    const c = parse({ setting_type: 'RISK_TIER_POLICY', target_key: 'ALL', new_value: { tiers: t } });
    expect(settingProblems(c, TODAY, FACILITIES)).toContain('MEDIUM max_score must equal HIGH min_score');
  });

  it('rejects a duplicated tier', () => {
    const t = tiers();
    t[2].risk_tier = 'MEDIUM';
    const c = parse({ setting_type: 'RISK_TIER_POLICY', target_key: 'ALL', new_value: { tiers: t } });
    expect(settingProblems(c, TODAY, FACILITIES)[0]).toMatch(/exactly once/);
  });

  it('rejects a retroactive effective date', () => {
    const c = parse({ setting_type: 'CARE_MANAGER_CAPACITY', target_key: 'cm@example.org', new_value: { daily_capacity: 40 }, effective_date: '2026-11-06' });
    expect(settingProblems(c, TODAY, FACILITIES)).toContain('effective_date is before the change was made');
  });

  it('rejects unknown facilities and allows an empty set', () => {
    const bad = parse({ setting_type: 'CARE_TEAM_ASSIGNMENT', target_key: 'cm@example.org', new_value: { facility_ids: ['FAC-X'] } });
    expect(settingProblems(bad, TODAY, FACILITIES)).toEqual(['unknown facility_ids: FAC-X']);
    const none = parse({ setting_type: 'CARE_TEAM_ASSIGNMENT', target_key: 'cm@example.org', new_value: { facility_ids: [] } });
    expect(settingProblems(none, TODAY, FACILITIES)).toEqual([]);
  });
});

describe('SettingChangeBody', () => {
  it('rejects bad capacity, uppercase email, and a non-ALL tier target', () => {
    const base = { change_reason: 'Testing a change', effective_date: '2026-11-10', client_request_id: ID };
    expect(SettingChangeBody.safeParse({ ...base, setting_type: 'CARE_MANAGER_CAPACITY', target_key: 'cm@example.org', new_value: { daily_capacity: 0 } }).success).toBe(false);
    expect(SettingChangeBody.safeParse({ ...base, setting_type: 'CARE_MANAGER_CAPACITY', target_key: 'cm@example.org', new_value: { daily_capacity: 2.5 } }).success).toBe(false);
    expect(SettingChangeBody.safeParse({ ...base, setting_type: 'CARE_MANAGER_CAPACITY', target_key: 'CM@Example.org', new_value: { daily_capacity: 40 } }).success).toBe(false);
    expect(SettingChangeBody.safeParse({ ...base, setting_type: 'RISK_TIER_POLICY', target_key: 'HIGH', new_value: { tiers: tiers() } }).success).toBe(false);
  });
});
