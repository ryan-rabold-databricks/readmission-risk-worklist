// Program tab: is outreach moving readmissions? Reads readmission_worklist_gold.readmission_outcome
// through the SQL warehouse on behalf of the signed-in user (*.obo.sql), so UC grants and
// policies apply. Genie joins this tab in Phase 6.

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  LineChart,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  useAnalyticsQuery,
} from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { useMemo } from 'react';
import { pct, type Me } from '../lib/api';
import { coerce, FacilityRow, ProgramKpis, TierEffectRow } from '../lib/rows';
import { ErrorAlert, TableSkeleton } from './WorklistPage';

const usd = (v: number) => v.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

function Delta({ actual, baseline, lowerIsBetter }: { actual: number | null; baseline: number | null; lowerIsBetter: boolean }) {
  if (actual === null || baseline === null) return null;
  const diff = (actual - baseline) * 100;
  const good = lowerIsBetter ? diff < 0 : diff > 0;
  return (
    <span className={good ? 'text-success' : 'text-destructive'}>
      {diff > 0 ? '+' : ''}
      {diff.toFixed(1)} pts vs prior year
    </span>
  );
}

function Kpi({ title, value, detail }: { title: string; value: string; detail: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl tabular-nums">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">{detail}</CardContent>
    </Card>
  );
}

export function ProgramPage({ me }: { me: Me }) {
  const base = useMemo(() => ({ catalog: sql.string(me.catalog), go_live: sql.date(me.programGoLive) }), [me]);
  const kpiParams = useMemo(() => ({ ...base, avg_cost: sql.double(me.avgReadmissionCost) }), [base, me]);
  const tierParams = useMemo(() => ({ catalog: sql.string(me.catalog) }), [me]);
  const kpis = coerce(ProgramKpis, useAnalyticsQuery('program_kpis', kpiParams));
  const facilities = coerce(FacilityRow, useAnalyticsQuery('program_by_facility', base));
  const tiers = coerce(TierEffectRow, useAnalyticsQuery('program_effect_by_tier', tierParams));
  const k = kpis.rows?.[0];

  return (
    <div className="space-y-6">
      {kpis.error && <ErrorAlert message={kpis.error} />}
      {kpis.loading && !k && <TableSkeleton />}
      {k && (
        <>
          <p className="text-sm text-muted-foreground">
            Program period: discharges from {k.program_start} (go-live {me.programGoLive}). Readmission rates use discharges whose
            30-day window has closed (through {k.matured_through}); baseline is the same span one year earlier. Data through{' '}
            {k.data_through}. Source: readmission_worklist_gold.readmission_outcome, refreshed by the daily cycle.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <Kpi
              title="30-day readmission rate"
              value={pct(k.program_readmit_rate)}
              detail={<>Prior year {pct(k.baseline_readmit_rate)}. <Delta actual={k.program_readmit_rate} baseline={k.baseline_readmit_rate} lowerIsBetter /></>}
            />
            <Kpi
              title="Reach rate"
              value={pct(k.reach_rate)}
              detail={`Assigned worklist items where the care manager spoke with the patient. ${k.worklist_items.toLocaleString()} items, ${k.overflow_items.toLocaleString()} overflow (over capacity). Median first contact ${k.median_first_contact_hours?.toFixed(0) ?? '-'} h after release.`}
            />
            <Kpi
              title="7-day follow-up rate"
              value={pct(k.program_followup_7d_rate)}
              detail={<>All discharges, attended within 7 days. Prior year {pct(k.baseline_followup_7d_rate)}. <Delta actual={k.program_followup_7d_rate} baseline={k.baseline_followup_7d_rate} lowerIsBetter={false} /></>}
            />
            <Kpi
              title="Estimated cost avoided"
              value={usd(k.est_cost_avoided)}
              detail={`${k.readmissions_avoided.toFixed(0)} readmissions avoided x ${usd(me.avgReadmissionCost)}. Per tier: reached vs not-reached readmission rate on matured assigned items. An estimate, not a causal measure.`}
            />
          </div>
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Readmission and 7-day follow-up rate by discharge month</CardTitle>
          <CardDescription>Program months start {me.programGoLive.slice(0, 7)}. Only months whose 30-day windows have all closed are shown.</CardDescription>
        </CardHeader>
        <CardContent>
          <LineChart
            queryKey="program_monthly"
            parameters={base}
            xKey="month"
            yKey={['readmit_rate', 'followup_7d_rate']}
            colorPalette="categorical"
            valueFormatter={(v) => (typeof v === 'number' ? pct(v) : String(v))}
            ariaLabel="Monthly readmission and 7-day follow-up rates"
            height={320}
          />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>By facility</CardTitle>
            <CardDescription>Highest program readmission rate first.</CardDescription>
          </CardHeader>
          <CardContent>
            {facilities.error && <ErrorAlert message={facilities.error} />}
            {facilities.loading && !facilities.rows && <TableSkeleton />}
            {facilities.rows && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Facility</TableHead>
                    <TableHead className="text-right">Readmit</TableHead>
                    <TableHead className="text-right">Prior year</TableHead>
                    <TableHead className="text-right">7-day f/u</TableHead>
                    <TableHead className="text-right">Reach</TableHead>
                    <TableHead className="text-right">Overflow</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {facilities.rows.map((f) => (
                    <TableRow key={f.facility_id}>
                      <TableCell>{f.facility_name}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(f.program_readmit_rate)}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">{pct(f.baseline_readmit_rate)}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(f.program_followup_7d_rate)}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(f.reach_rate)}</TableCell>
                      <TableCell className="text-right tabular-nums">{f.overflow_items}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Reached patients readmit less at the same predicted risk</CardTitle>
            <CardDescription>Worklist items with a closed 30-day window, by tier and outreach result.</CardDescription>
          </CardHeader>
          <CardContent>
            {tiers.error && <ErrorAlert message={tiers.error} />}
            {tiers.loading && !tiers.rows && <TableSkeleton />}
            {tiers.rows && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tier</TableHead>
                    <TableHead>Outreach</TableHead>
                    <TableHead className="text-right">Items</TableHead>
                    <TableHead className="text-right">Readmit</TableHead>
                    <TableHead className="text-right">Predicted</TableHead>
                    <TableHead className="text-right">7-day f/u</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tiers.rows.map((t) => (
                    <TableRow key={`${t.risk_tier}-${t.outreach_group}`}>
                      <TableCell>{t.risk_tier}</TableCell>
                      <TableCell>{t.outreach_group}</TableCell>
                      <TableCell className="text-right tabular-nums">{t.items.toLocaleString()}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(t.readmit_rate)}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">{pct(t.mean_predicted_risk)}</TableCell>
                      <TableCell className="text-right tabular-nums">{pct(t.followup_7d_rate)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
