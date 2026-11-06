// Worklist tab: today's prioritized outreach list for the signed-in care manager's
// facilities, an item drawer with drivers and the AI-drafted brief, and call logging.

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
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
  ToggleGroup,
  ToggleGroupItem,
} from '@databricks/appkit-ui/react';
import { useMemo, useState } from 'react';
import { api, ApiError, dateTime, pct, useApi, type Me } from '../lib/api';

interface WorklistItem {
  worklist_item_id: string;
  facility_id: string;
  worklist_date: string;
  assignment_status: 'ASSIGNED' | 'OVERFLOW';
  assigned_care_manager: string | null;
  patient_display_name: string;
  phone: string | null;
  risk_score: number;
  risk_tier: string;
  top_drivers: string[];
  outreach_brief: string | null;
  due_at: string;
  created_at: string;
  attempts: number;
  last_activity_type: string | null;
  last_activity_ts: string | null;
  next_step_due_at: string | null;
  reached: boolean;
}

interface Activity {
  activity_id: string;
  care_manager_email: string;
  activity_type: string;
  activity_ts: string;
  next_step_due_at: string | null;
  note: string | null;
}

const ACTIVITY_LABELS: Record<string, string> = {
  NO_ANSWER: 'No answer',
  LEFT_VOICEMAIL: 'Left voicemail',
  REACHED: 'Reached',
  FOLLOWUP_BOOKED: 'Follow-up booked',
  DECLINED: 'Declined',
  UNREACHABLE: 'Unreachable',
};
const NEEDS_NEXT_STEP = new Set(['NO_ANSWER', 'LEFT_VOICEMAIL']);

type Filter = 'mine' | 'open' | 'overflow' | 'all';

function status(item: WorklistItem): { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' } {
  const t = item.last_activity_type;
  if (!t) return isOverdue(item) ? { label: 'Not started, overdue', variant: 'destructive' } : { label: 'Not started', variant: 'outline' };
  if (t === 'FOLLOWUP_BOOKED') return { label: 'Follow-up booked', variant: 'default' };
  if (t === 'REACHED' || t === 'DECLINED') return { label: ACTIVITY_LABELS[t], variant: 'secondary' };
  if (t === 'UNREACHABLE') return { label: 'Unreachable', variant: 'secondary' };
  return { label: `Attempt ${item.attempts}, ${ACTIVITY_LABELS[t].toLowerCase()}`, variant: isOverdue(item) ? 'destructive' : 'outline' };
}

function isOpen(item: WorklistItem) {
  return !item.reached && item.last_activity_type !== 'UNREACHABLE';
}

function isOverdue(item: WorklistItem) {
  const due = item.next_step_due_at ?? item.due_at;
  return isOpen(item) && Date.parse(due) < Date.now();
}

export function WorklistPage({ me }: { me: Me }) {
  const dates = useApi<string[]>('/api/worklist/dates');
  const [chosenDate, setDate] = useState<string | null>(null);
  const date = chosenDate ?? dates.data?.[0] ?? null;
  const [filter, setFilter] = useState<Filter>('mine');
  const [selected, setSelected] = useState<string | null>(null);
  const list = useApi<WorklistItem[]>(date ? `/api/worklist?date=${date}` : null);

  const rows = useMemo(() => {
    const all = list.data ?? [];
    if (filter === 'mine') return all.filter((i) => i.assigned_care_manager === me.email);
    if (filter === 'open') return all.filter(isOpen);
    if (filter === 'overflow') return all.filter((i) => i.assignment_status === 'OVERFLOW');
    return all;
  }, [list.data, filter, me.email]);
  const mine = (list.data ?? []).filter((i) => i.assigned_care_manager === me.email);
  const mineOpen = mine.filter(isOpen).length;
  const overdue = mine.filter(isOverdue).length;

  if (dates.error) return <ErrorAlert message={dates.error} />;
  if (dates.data && dates.data.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>No worklist for you</EmptyTitle>
          <EmptyDescription>
            {me.email} is not on the care team roster for any facility in the last 30 worklist days. Leadership assigns
            facilities in Program Settings; changes take effect on the next daily cycle.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <Label htmlFor="worklist-date">Worklist day</Label>
          <Select value={date ?? undefined} onValueChange={setDate}>
            <SelectTrigger id="worklist-date" className="w-44">
              <SelectValue placeholder="Loading days" />
            </SelectTrigger>
            <SelectContent>
              {(dates.data ?? []).map((d) => (
                <SelectItem key={d} value={d}>
                  {d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <ToggleGroup type="single" value={filter} onValueChange={(v) => v && setFilter(v as Filter)} variant="outline">
          <ToggleGroupItem value="mine">Assigned to me</ToggleGroupItem>
          <ToggleGroupItem value="open">Open at my facilities</ToggleGroupItem>
          <ToggleGroupItem value="overflow">Overflow</ToggleGroupItem>
          <ToggleGroupItem value="all">All</ToggleGroupItem>
        </ToggleGroup>
        <div className="ml-auto flex gap-6 text-sm">
          <Stat label="Assigned to me" value={mine.length} />
          <Stat label="Still open" value={mineOpen} />
          <Stat label="Overdue" value={overdue} tone={overdue ? 'destructive' : undefined} />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Patients to call, highest risk first</CardTitle>
          <CardDescription>
            Discharged the day before {date ?? '...'}; released 12:00 UTC. Status comes from calls logged here (Lakebase), so it
            updates as soon as you log a call.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {list.error && <ErrorAlert message={list.error} />}
          {(list.loading || dates.loading) && !list.data && <TableSkeleton />}
          {list.data && rows.length === 0 && (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>Nothing in this view</EmptyTitle>
                <EmptyDescription>Try another filter or worklist day.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
          {rows.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Patient</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Top driver</TableHead>
                  <TableHead>Facility</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Assigned to</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((item) => {
                  const s = status(item);
                  return (
                    <TableRow key={item.worklist_item_id} className="cursor-pointer" onClick={() => setSelected(item.worklist_item_id)}>
                      <TableCell>
                        <button type="button" className="font-medium text-left underline-offset-4 hover:underline" onClick={() => setSelected(item.worklist_item_id)}>
                          {item.patient_display_name}
                        </button>
                        <div className="text-xs text-muted-foreground">{item.phone ?? 'No phone on file'}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={item.risk_tier === 'HIGH' ? 'destructive' : 'secondary'}>{item.risk_tier}</Badge>
                        <span className="ml-2 tabular-nums">{pct(item.risk_score, 0)}</span>
                      </TableCell>
                      <TableCell className="max-w-64 truncate">{item.top_drivers[0] ?? '-'}</TableCell>
                      <TableCell>{item.facility_id}</TableCell>
                      <TableCell className="whitespace-nowrap">{dateTime(item.next_step_due_at ?? item.due_at)}</TableCell>
                      <TableCell>
                        <Badge variant={s.variant}>{s.label}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{item.assigned_care_manager ?? 'Unassigned (overflow)'}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ItemSheet itemId={selected} onClose={() => setSelected(null)} onLogged={list.reload} />
    </div>
  );
}

function ItemSheet({ itemId, onClose, onLogged }: { itemId: string | null; onClose: () => void; onLogged: () => void }) {
  const detail = useApi<{ item: WorklistItem; history: Activity[] }>(itemId ? `/api/worklist/items/${itemId}` : null);
  const item = detail.data?.item.worklist_item_id === itemId ? detail.data.item : null;
  return (
    <Sheet open={itemId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{item ? item.patient_display_name : 'Loading patient'}</SheetTitle>
          <SheetDescription>
            {item ? `${item.phone ?? 'No phone on file'} - ${item.facility_id} - worklist ${item.worklist_date}` : ' '}
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4 pb-6">
          {detail.error && <ErrorAlert message={detail.error} />}
          {!item && !detail.error && <TableSkeleton />}
          {item && detail.data && (
            <>
              <div className="flex flex-wrap gap-2 items-center">
                <Badge variant={item.risk_tier === 'HIGH' ? 'destructive' : 'secondary'}>{item.risk_tier} risk</Badge>
                <span className="text-sm">{pct(item.risk_score, 0)} predicted 30-day readmission risk</span>
                <Badge variant="outline">Call by {dateTime(item.due_at)}</Badge>
              </div>
              <section className="space-y-1">
                <h3 className="text-sm font-semibold">Why this patient is on the list</h3>
                <ul className="list-disc pl-5 text-sm">
                  {item.top_drivers.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              </section>
              <section className="space-y-1">
                <h3 className="text-sm font-semibold">Outreach brief</h3>
                {item.outreach_brief ? (
                  <>
                    <p className="text-sm whitespace-pre-line">{item.outreach_brief}</p>
                    <p className="text-xs text-muted-foreground">AI-drafted from the risk drivers only (no chart access). Verify before acting.</p>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">No brief for this day (briefs are drafted for the most recent worklist days).</p>
                )}
              </section>
              <Separator />
              <LogCallForm itemId={item.worklist_item_id} onLogged={() => { detail.reload(); onLogged(); }} />
              <Separator />
              <section className="space-y-2">
                <h3 className="text-sm font-semibold">Outreach history</h3>
                {detail.data.history.length === 0 && <p className="text-sm text-muted-foreground">No calls logged yet.</p>}
                {detail.data.history.map((a) => (
                  <div key={a.activity_id} className="text-sm border-l-2 pl-3">
                    <div className="font-medium">{ACTIVITY_LABELS[a.activity_type] ?? a.activity_type}</div>
                    <div className="text-xs text-muted-foreground">
                      {dateTime(a.activity_ts)} by {a.care_manager_email}
                      {a.next_step_due_at ? ` - next attempt ${dateTime(a.next_step_due_at)}` : ''}
                    </div>
                    {a.note && <div className="text-sm mt-1">{a.note}</div>}
                  </div>
                ))}
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function defaultNextStep() {
  const d = new Date(Date.now() + 4 * 3600_000);
  d.setMinutes(0, 0, 0);
  return toLocalInput(d);
}

function toLocalInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function LogCallForm({ itemId, onLogged }: { itemId: string; onLogged: () => void }) {
  const [activityType, setActivityType] = useState<string>('REACHED');
  const [nextStep, setNextStep] = useState(defaultNextStep());
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  // One request ID per intended call log, so a retried submit cannot log it twice.
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await api(`/api/worklist/items/${itemId}/outreach`, {
        method: 'POST',
        body: JSON.stringify({
          client_request_id: requestId,
          activity_type: activityType,
          next_step_due_at: NEEDS_NEXT_STEP.has(activityType) && nextStep ? new Date(nextStep).toISOString() : null,
          note: note.trim() || null,
        }),
      });
      setMessage({ ok: true, text: `${ACTIVITY_LABELS[activityType]} logged.` });
      setNote('');
      setRequestId(crypto.randomUUID());
      onLogged();
    } catch (err) {
      const issues = err instanceof ApiError && err.issues.length ? `: ${err.issues.join('; ')}` : '';
      setMessage({ ok: false, text: `${(err as Error).message}${issues}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="space-y-3" onSubmit={(e) => void submit(e)}>
      <h3 className="text-sm font-semibold">Log a call</h3>
      <div className="space-y-1">
        <Label htmlFor="activity-type">Outcome</Label>
        <Select value={activityType} onValueChange={setActivityType}>
          <SelectTrigger id="activity-type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(ACTIVITY_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>
                {v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {NEEDS_NEXT_STEP.has(activityType) && (
        <div className="space-y-1">
          <Label htmlFor="next-step">Next attempt</Label>
          <Input id="next-step" type="datetime-local" value={nextStep} onChange={(e) => setNextStep(e.target.value)} />
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="note">Note (optional)</Label>
        <Textarea id="note" maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything the next caller should know" />
      </div>
      <Button type="submit" disabled={saving}>
        {saving ? 'Saving' : 'Log call'}
      </Button>
      {message && (
        <p className={message.ok ? 'text-sm text-muted-foreground' : 'text-sm text-destructive'} role="status">
          {message.text}
        </p>
      )}
    </form>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'destructive' }) {
  return (
    <div>
      <div className={`text-2xl font-semibold tabular-nums ${tone === 'destructive' ? 'text-destructive' : ''}`}>{value}</div>
      <div className="text-muted-foreground">{label}</div>
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }, (_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

export function ErrorAlert({ message }: { message: string }) {
  return (
    <Alert variant="destructive">
      <AlertTitle>Could not load</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
