// Program Settings tab (care_mgmt_leadership): risk tier cut-offs and SLAs, care team
// facilities and capacity. Each save appends one change to Lakebase; the next daily
// cycle's pipeline validates and applies it from its effective date (DECISIONS.md #51).
// "In effect" values are read from Unity Catalog on behalf of the user.

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
  Input,
  Label,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
  useAnalyticsQuery,
} from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { useMemo, useState } from 'react';
import type { z } from 'zod';
import { addDays, api, ApiError, dateTime, todayUtc, useApi, type Me } from '../lib/api';
import { CareTeamRow, ChangeStatusRow, coerce, FacilityOption, PolicyRow as PolicyRowSchema } from '../lib/rows';
import { ErrorAlert, TableSkeleton } from './WorklistPage';

interface ChangeRow {
  change_id: string;
  setting_type: string;
  target_key: string;
  new_value_json: unknown;
  change_reason: string | null;
  effective_date: string;
  changed_by: string;
  changed_at: string;
}

type TierName = 'HIGH' | 'MEDIUM' | 'LOW';
interface TierDraft {
  sla: number;
  include: boolean;
}

const TYPE_LABELS: Record<string, string> = {
  RISK_TIER_POLICY: 'Risk tiers',
  CARE_TEAM_ASSIGNMENT: 'Facilities',
  CARE_MANAGER_CAPACITY: 'Daily capacity',
};

async function submitChange(body: object) {
  return api<{ change_id: string }>('/api/settings/changes', {
    method: 'POST',
    body: JSON.stringify({ client_request_id: crypto.randomUUID(), ...body }),
  });
}

function errorText(err: unknown) {
  return err instanceof ApiError && err.issues.length ? `${err.message}: ${err.issues.join('; ')}` : (err as Error).message;
}

export function SettingsPage({ me }: { me: Me }) {
  if (!me.isLeader) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Program Settings is for care management leadership</EmptyTitle>
          <EmptyDescription>Ask an administrator to add {me.email} to the care_mgmt_leadership group.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }
  return <SettingsEditor me={me} />;
}

function SettingsEditor({ me }: { me: Me }) {
  const tomorrow = addDays(todayUtc(), 1);
  const changes = useApi<ChangeRow[]>('/api/settings/changes');
  const catalogParams = useMemo(() => ({ catalog: sql.string(me.catalog) }), [me]);
  const teamParams = useMemo(() => ({ catalog: sql.string(me.catalog), as_of: sql.date(tomorrow) }), [me, tomorrow]);
  const policy = coerce(PolicyRowSchema, useAnalyticsQuery('settings_risk_tier_policy', catalogParams));
  const team = coerce(CareTeamRow, useAnalyticsQuery('settings_care_team', teamParams));
  const statuses = coerce(ChangeStatusRow, useAnalyticsQuery('settings_change_status', catalogParams));
  const facilities = coerce(FacilityOption, useAnalyticsQuery('facilities', catalogParams));
  const [editing, setEditing] = useState<{ email: string; facilityIds: string[]; capacity: number | null } | null>(null);

  const onSaved = () => changes.reload();

  return (
    <div className="space-y-6">
      <Alert>
        <AlertTitle>Changes apply on the next daily cycle</AlertTitle>
        <AlertDescription>
          Every save is recorded with who, when, and why. The pipeline re-validates each change and applies it from its effective
          date; worklists already released are never rebuilt. The change log below shows the pipeline&apos;s result.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Risk tiers</CardTitle>
          <CardDescription>Cut-offs on predicted 30-day readmission risk, outreach SLA from worklist release, and which tiers go on the worklist.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {policy.error && <ErrorAlert message={policy.error} />}
          {policy.loading && !policy.rows && <TableSkeleton />}
          {policy.rows && (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tier</TableHead>
                    <TableHead>Score range</TableHead>
                    <TableHead>SLA</TableHead>
                    <TableHead>On worklist</TableHead>
                    <TableHead>Effective</TableHead>
                    <TableHead>Set by</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {policy.rows.map((t) => (
                    <TableRow key={`${t.risk_tier}-${t.effective_date}`}>
                      <TableCell>{t.risk_tier}</TableCell>
                      <TableCell className="tabular-nums">
                        {t.min_score.toFixed(2)} - {t.max_score.toFixed(2)}
                      </TableCell>
                      <TableCell>{t.outreach_sla_hours} h</TableCell>
                      <TableCell>{t.include_in_worklist ? 'Yes' : 'No'}</TableCell>
                      <TableCell>
                        {t.effective_date}
                        {t.expiration_date ? ` to ${t.expiration_date}` : ''}
                        {t.effective_date > todayUtc() && <Badge variant="outline" className="ml-2">Scheduled</Badge>}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{t.source.startsWith('seed:') ? 'Initial seed' : t.set_by}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <TierPolicyForm current={policy.rows} defaultDate={tomorrow} onSaved={onSaved} />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Care team</CardTitle>
          <CardDescription>Facilities each care manager covers and how many new worklist items they can take per day, as of {tomorrow}.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {team.error && <ErrorAlert message={team.error} />}
          {team.loading && !team.rows && <TableSkeleton />}
          {team.rows && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Care manager</TableHead>
                  <TableHead>Facilities</TableHead>
                  <TableHead className="text-right">Daily capacity</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {team.rows.map((m) => (
                  <TableRow key={m.care_manager_email}>
                    <TableCell>{m.care_manager_email}</TableCell>
                    <TableCell>{m.facility_ids.length ? m.facility_ids.join(', ') : 'None'}</TableCell>
                    <TableCell className="text-right tabular-nums">{m.daily_capacity ?? '-'}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => setEditing({ email: m.care_manager_email, facilityIds: m.facility_ids, capacity: m.daily_capacity })}>
                        Edit
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <Button variant="outline" onClick={() => setEditing({ email: '', facilityIds: [], capacity: null })}>
            Add care manager
          </Button>
        </CardContent>
      </Card>

      <CareManagerDialog
        value={editing}
        facilities={facilities.rows ?? []}
        defaultDate={tomorrow}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          onSaved();
        }}
      />

      <Card>
        <CardHeader>
          <CardTitle>Change log</CardTitle>
          <CardDescription>Most recent first. Pipeline status appears after the next daily cycle.</CardDescription>
        </CardHeader>
        <CardContent>
          {changes.error && <ErrorAlert message={changes.error} />}
          {changes.loading && !changes.data && <TableSkeleton />}
          {changes.data && changes.data.length === 0 && <p className="text-sm text-muted-foreground">No changes yet; the seeds are in effect.</p>}
          {changes.data && changes.data.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Setting</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Effective</TableHead>
                  <TableHead>By</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Pipeline</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {changes.data.map((c) => {
                  const s = statuses.rows?.find((x) => x.change_id === c.change_id);
                  return (
                    <TableRow key={c.change_id}>
                      <TableCell className="whitespace-nowrap">{dateTime(c.changed_at)}</TableCell>
                      <TableCell>{TYPE_LABELS[c.setting_type] ?? c.setting_type}</TableCell>
                      <TableCell>{c.target_key}</TableCell>
                      <TableCell>{c.effective_date}</TableCell>
                      <TableCell>{c.changed_by}</TableCell>
                      <TableCell className="max-w-64 truncate">{c.change_reason}</TableCell>
                      <TableCell>
                        {s ? (
                          <Badge variant={s.status === 'APPLIED' ? 'default' : s.status === 'REJECTED' ? 'destructive' : 'secondary'} title={s.status_reason ?? undefined}>
                            {s.status}
                          </Badge>
                        ) : (
                          <Badge variant="outline">Waiting for pipeline</Badge>
                        )}
                        {s?.status_reason && <div className="text-xs text-muted-foreground mt-1">{s.status_reason}</div>}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

type PolicyRow = z.infer<typeof PolicyRowSchema>;

function TierPolicyForm({ current, defaultDate, onSaved }: { current: PolicyRow[]; defaultDate: string; onSaved: () => void }) {
  // Start from the latest version (scheduled if any, otherwise in effect).
  const latest = useMemo(() => {
    const last = current.reduce((m, r) => (r.effective_date > m ? r.effective_date : m), '');
    return new Map(current.filter((r) => r.effective_date === last).map((r) => [r.risk_tier as TierName, r]));
  }, [current]);
  const [open, setOpen] = useState(false);
  const [highMin, setHighMin] = useState(latest.get('HIGH')?.min_score ?? 0.3);
  const [mediumMin, setMediumMin] = useState(latest.get('MEDIUM')?.min_score ?? 0.18);
  const [tiers, setTiers] = useState<Record<TierName, TierDraft>>(() => ({
    HIGH: { sla: latest.get('HIGH')?.outreach_sla_hours ?? 24, include: latest.get('HIGH')?.include_in_worklist ?? true },
    MEDIUM: { sla: latest.get('MEDIUM')?.outreach_sla_hours ?? 72, include: latest.get('MEDIUM')?.include_in_worklist ?? true },
    LOW: { sla: latest.get('LOW')?.outreach_sla_hours ?? 168, include: latest.get('LOW')?.include_in_worklist ?? false },
  }));
  const [effective, setEffective] = useState(defaultDate);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        Change tiers
      </Button>
    );
  }

  const round2 = (n: number) => Math.round(n * 100) / 100;
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      // Two cut-offs define all three ranges, so the tiers are always contiguous.
      const h = round2(highMin);
      const m = round2(mediumMin);
      await submitChange({
        setting_type: 'RISK_TIER_POLICY',
        target_key: 'ALL',
        effective_date: effective,
        change_reason: reason,
        new_value: {
          tiers: [
            { risk_tier: 'HIGH', min_score: h, max_score: 1, outreach_sla_hours: tiers.HIGH.sla, include_in_worklist: tiers.HIGH.include },
            { risk_tier: 'MEDIUM', min_score: m, max_score: h, outreach_sla_hours: tiers.MEDIUM.sla, include_in_worklist: tiers.MEDIUM.include },
            { risk_tier: 'LOW', min_score: 0, max_score: m, outreach_sla_hours: tiers.LOW.sla, include_in_worklist: tiers.LOW.include },
          ],
        },
      });
      setMessage({ ok: true, text: `Saved. Takes effect for worklists from ${effective} once the pipeline applies it.` });
      setReason('');
      onSaved();
    } catch (err) {
      setMessage({ ok: false, text: errorText(err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="space-y-4 border rounded-md p-4" onSubmit={(e) => void save(e)}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="high-min">HIGH starts at (risk score)</Label>
          <Input id="high-min" type="number" step="0.01" min="0.02" max="0.99" value={highMin} onChange={(e) => setHighMin(Number(e.target.value))} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="medium-min">MEDIUM starts at (risk score)</Label>
          <Input id="medium-min" type="number" step="0.01" min="0.01" max="0.98" value={mediumMin} onChange={(e) => setMediumMin(Number(e.target.value))} />
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {(['HIGH', 'MEDIUM', 'LOW'] as const).map((t) => (
          <div key={t} className="space-y-2">
            <Label htmlFor={`sla-${t}`}>{t} SLA (hours)</Label>
            <Input id={`sla-${t}`} type="number" min="1" max="336" step="1" value={tiers[t].sla} onChange={(e) => setTiers({ ...tiers, [t]: { ...tiers[t], sla: Number(e.target.value) } })} />
            <div className="flex items-center gap-2">
              <Switch id={`inc-${t}`} checked={tiers[t].include} onCheckedChange={(v) => setTiers({ ...tiers, [t]: { ...tiers[t], include: v } })} />
              <Label htmlFor={`inc-${t}`}>On worklist</Label>
            </div>
          </div>
        ))}
      </div>
      <ChangeMeta effective={effective} setEffective={setEffective} reason={reason} setReason={setReason} minDate={todayUtc()} />
      <div className="flex gap-2">
        <Button type="submit" disabled={saving || mediumMin >= highMin || reason.trim().length < 5}>
          {saving ? 'Saving' : 'Save tier change'}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          Close
        </Button>
      </div>
      {mediumMin >= highMin && <p className="text-sm text-destructive">MEDIUM must start below HIGH.</p>}
      {message && <p className={message.ok ? 'text-sm text-muted-foreground' : 'text-sm text-destructive'} role="status">{message.text}</p>}
    </form>
  );
}

function ChangeMeta(props: { effective: string; setEffective: (v: string) => void; reason: string; setReason: (v: string) => void; minDate: string }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div className="space-y-1">
        <Label htmlFor="effective">Effective date (UTC)</Label>
        <Input id="effective" type="date" min={props.minDate} value={props.effective} onChange={(e) => props.setEffective(e.target.value)} />
      </div>
      <div className="space-y-1 md:col-span-2">
        <Label htmlFor="reason">Reason (required)</Label>
        <Textarea id="reason" maxLength={500} value={props.reason} onChange={(e) => props.setReason(e.target.value)} placeholder="Why this change, for the audit trail" />
      </div>
    </div>
  );
}

function CareManagerDialog(props: {
  value: { email: string; facilityIds: string[]; capacity: number | null } | null;
  facilities: { facility_id: string; facility_name: string }[];
  defaultDate: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  return (
    <Dialog open={props.value !== null} onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{props.value?.email ? `Edit ${props.value.email}` : 'Add care manager'}</DialogTitle>
          <DialogDescription>Saves one change per setting you edit (facilities, capacity).</DialogDescription>
        </DialogHeader>
        {props.value && <CareManagerForm key={props.value.email} {...props} value={props.value} />}
      </DialogContent>
    </Dialog>
  );
}

function CareManagerForm({ value, facilities, defaultDate, onSaved }: {
  value: { email: string; facilityIds: string[]; capacity: number | null };
  facilities: { facility_id: string; facility_name: string }[];
  defaultDate: string;
  onSaved: () => void;
}) {
  const [email, setEmail] = useState(value.email);
  const [selected, setSelected] = useState<string[]>(value.facilityIds);
  const [capacity, setCapacity] = useState<number>(value.capacity ?? 25);
  const [effective, setEffective] = useState(defaultDate);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const facilitiesChanged = [...selected].sort().join() !== [...value.facilityIds].sort().join();
  const capacityChanged = capacity !== value.capacity;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const target = email.trim().toLowerCase();
    const meta = { target_key: target, effective_date: effective, change_reason: reason };
    try {
      if (facilitiesChanged) await submitChange({ ...meta, setting_type: 'CARE_TEAM_ASSIGNMENT', new_value: { facility_ids: selected } });
      if (capacityChanged) await submitChange({ ...meta, setting_type: 'CARE_MANAGER_CAPACITY', new_value: { daily_capacity: capacity } });
      onSaved();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="space-y-4" onSubmit={(e) => void save(e)}>
      <div className="space-y-1">
        <Label htmlFor="cm-email">Care manager email</Label>
        <Input id="cm-email" type="email" value={email} disabled={Boolean(value.email)} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Facilities</legend>
        {facilities.map((f) => (
          <div key={f.facility_id} className="flex items-center gap-2">
            <Checkbox
              id={`fac-${f.facility_id}`}
              checked={selected.includes(f.facility_id)}
              onCheckedChange={(v) => setSelected(v ? [...selected, f.facility_id] : selected.filter((x) => x !== f.facility_id))}
            />
            <Label htmlFor={`fac-${f.facility_id}`}>{f.facility_name}</Label>
          </div>
        ))}
      </fieldset>
      <div className="space-y-1">
        <Label htmlFor="cm-capacity">New worklist items per day</Label>
        <Input id="cm-capacity" type="number" min="1" max="500" step="1" value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} />
      </div>
      <ChangeMeta effective={effective} setEffective={setEffective} reason={reason} setReason={setReason} minDate={todayUtc()} />
      <Button type="submit" disabled={saving || (!facilitiesChanged && !capacityChanged) || reason.trim().length < 5 || !email.includes('@')}>
        {saving ? 'Saving' : 'Save'}
      </Button>
      {error && <p className="text-sm text-destructive" role="status">{error}</p>}
    </form>
  );
}
