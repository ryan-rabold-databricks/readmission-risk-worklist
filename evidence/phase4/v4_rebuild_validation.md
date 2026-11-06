# Phase 4 follow-up: simulator v4 program response, rebuild, and minimum-necessary sync

Workspace `fevm-classic-stable`, catalog `rtr_demo_catalog`, 2026-11-06. All data synthetic.
Decisions #45-#49. Raw output: `simulator_v4_dry_run.txt`, `simulator_v4_reland*.log`, `rebuild_reset.log`,
`pipeline_full_refresh_v4.log`, `program_backfill_v4.log`, `outreach_sim_v4_reconcile.log`, `daily_cycle_v4.log`,
`v4_data_checks.raw.txt`, `v4_rebuild_consistency.raw.txt`, `v4_program_effect.raw.txt`, `publish_snapshot_test.log`.

## Rebuild steps

| # | Step | Result |
|---|---|---|
| 1 | Clear landing manifests and extract folders | Manifests removed by the agent; the CLI hit S3 throttling on the folders, so the simulator's own cleanup removed the rest |
| 2 | `dev_readmit_source_simulator` (generator v4) | Attempt 1 timed out at the 60-min job limit while deleting folders one file at a time; attempt 2 removed the last 117 and landed 735 dates (2024-11-01..2026-11-05). Input: 4,981 reached worklist items. Program response: 3,752 reached index stays, 1,468 care-manager follow-ups, 240 readmissions prevented |
| 3 | Reset gold program tables and model aliases | Run by the author (the agent's call was blocked): 0 rows in `discharge_risk_score`, `care_worklist`, `care_team_roster`; no aliases; versions kept |
| 4 | Pipeline full refresh | Update 1dc91f COMPLETED in about 1.5 min |
| 5 | `dev_readmit_program_backfill` | SUCCESS. Seven monthly models v10-v16, all promoted through the gates; v10 (as of 2026-05-01) reproduces the v3-era first model exactly (AUC 0.7498, slope 1.064), confirming pre-go-live data is unchanged. 638 of 672 briefs (34 empty responses, under the 10% limit) |
| 6 | `dev_readmit_outreach_simulator` reconcile | 8,243 assigned items, 20,800 planned activities, 605 stale simulator rows deleted, 1,789 inserted; 1,355 FOLLOWUP_BOOKED; reach rate 0.597 |
| 7 | `dev_readmit_daily_cycle` | SUCCESS; the 34 failed briefs regenerated (0 errors); publish: UC 1,465 / 39 rows = Postgres 1,465 / 39 (worklist total / 2026-11-06), roster 150 / 5 |

## Feature leakage guard (#47)

Care-manager bookings in the EHR after go-live: 1,427 booked after the worklist release (of 25,226 appointments).
Discharges whose `followup_scheduled_7d` is true only because of a post-release booking: **0**.

## Consistency of the one-pass rebuild (#45)

The simulator used the reach set from the previous worklists (R0); the rebuilt worklists produced R1.

| Reach set comparison (worklist days before 2026-11-05) | Items |
|---|---|
| Same item, same reach time | 4,822 (95.3%) |
| Reached in R0 only | 159 |
| Reached in R1 only | 80 |

The effects that matter are consistent: of 1,438 care-manager bookings in the EHR, 1,425 match a REACHED call in the
app; 13 (0.9%) have no matching call (11 of them are discharges no longer on the rebuilt worklist). No second pass.
The CDF history shows the reconcile as 605 deletes alongside 21,405 inserts.

## Program effect

Matured 30-day labels, worklist items since go-live. Reach is assigned at random within a tier by the outreach
simulator, so reached and not-reached items have the same predicted risk.

| Tier | Group | Items | Readmitted | 7-day follow-up attended | Mean predicted |
|---|---|---|---|---|---|
| HIGH | reached | 2,567 | 34.6% | 54.9% | 39.4% |
| HIGH | assigned, not reached | 1,514 | 39.1% | 36.8% | 39.3% |
| MEDIUM | reached | 1,552 | 18.5% | 63.1% | 24.0% |
| MEDIUM | assigned, not reached | 1,269 | 22.6% | 45.1% | 24.1% |
| MEDIUM | overflow (not worked) | 273 | 17.9% | 46.5% | 20.0% |

System-wide, same season (May-Sep discharges): readmission 14.98% (2025) -> 14.33% (2026); 7-day follow-up attended
47.0% -> 50.8%. A Nov-Apr vs May-Oct comparison (16.11% -> 14.35%) overstates the effect because of the winter
respiratory surge.

## Minimum-necessary sync and internal storage (#46, #48)

| Check | Result |
|---|---|
| Postgres `care_worklist_synced` | 13 columns (was 24), 1,465 rows for the latest 30 worklist days (was 8,802 rows, full history) |
| Snapshot refresh time | about 27 s per table (pipeline events, `publish_snapshot_test.log`) |
| Synced-table storage | deployed spec `storage_schema: readmission_worklist_sync_internal` (bundle deployment state); snapshot pipelines create no visible tables |
| `readmission_worklist_gold` | only data-product objects: tables, `*_active` views, `*_synced` tables, `discharge_features` |
