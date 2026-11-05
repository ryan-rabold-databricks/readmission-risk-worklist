# Phase 4 evidence: Lakebase project, synced tables, app schema, CDF feed

Workspace `fevm-classic-stable`, catalog `rtr_demo_catalog`, run 2026-11-05. All data synthetic.
Raw output: `setup_run_*.log`, `outreach_sim_run_*.log`, `daily_cycle_with_publish.log`,
`postgres_validation.raw.txt`, `cdf_landing_validation.raw.txt`.

## Provisioning (bundle, DECISIONS.md #40)

`bundle deploy -t dev` created `postgres_projects.readmission_worklist`, `postgres_databases.readmission_worklist_db`,
`postgres_synced_tables.care_worklist_synced` and `care_team_roster_synced` (6 created, 0 deleted). A follow-up
`bundle plan` showed no drift on Lakebase resources (only jobs change, from the per-deploy wheel version).

| Check | Result |
|---|---|
| Project | `readmission-worklist`, Postgres 17, autoscaling 0.5-2 CU, suspend after 300 s, owner the deploying user |
| Database | resource `readmission-worklist`, Postgres name `readmission_worklist`, owner role `ryan-rabold` |
| Synced tables | both `SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE` after the initial snapshot |
| Postgres row counts | `care_worklist_synced` 8,802 = UC `care_worklist` 8,802; `care_team_roster_synced` 945 |
| Postgres schemas | `readmission_worklist_gold` (synced only), `readmission_worklist_app` (app-owned) |

## App schema and CDF feed (`dev_readmit_setup`, DECISIONS.md #42, #43)

| Run | Result |
|---|---|
| 1 | Failed: `Invalid cdf_config_id 'readmission-worklist-app'. Must match [a-z][a-z0-9_]{0,62}` (schema DDL had already applied) |
| 2 | Success: REPLICA IDENTITY FULL verified on `outreach_activity` and `program_setting_change`; CDF config `readmission_worklist_app` -> `rtr_demo_catalog.readmission_worklist_app_bronze` |
| 3 (rerun) | Success, identical output: idempotent |

CDF statuses: both tables `CDF_STATE_STREAMING`, landing as `lb_outreach_activity_history` and
`lb_program_setting_change_history`. No feed exists on the `readmission_worklist_gold` Postgres schema
(the code refuses it; unit test `test_cdf_feed_on_synced_gold_schema_is_refused`).

## Outreach simulator (`dev_readmit_outreach_simulator`, DECISIONS.md #44)

| Run | Assigned items | Planned | Inserted | Reach rate |
|---|---|---|---|---|
| 1 | 8,318 | 19,616 | 19,616 | 0.599 |
| 2 (rerun) | 8,318 | 19,616 | 0 | 0.599 |

By type: NO_ANSWER 7,996, REACHED 4,981, LEFT_VOICEMAIL 3,709, UNREACHABLE 2,549, DECLINED 381. No
FOLLOWUP_BOOKED rows: every follow-up appointment in the EHR data was booked before its worklist release.
Worklist day 2026-11-05 has no outreach (cutoff = its release), so it is left for the live demo.

## CDF landing in Unity Catalog

| Check | Result |
|---|---|
| `lb_outreach_activity_history` rows | 19,616, all `_pg_change_type = insert`, 19,616 distinct `activity_id` and `client_request_id` |
| Matches Postgres | 19,616 = `readmission_worklist_app.outreach_activity` |
| Orphan `worklist_item_id` (not in `care_worklist`) | 0 |
| Landing latency | rows written 22:43:2x UTC, `_timestamp` 22:43:27-22:43:28 |
| Type mapping | Postgres `UUID` -> UC `BINARY` (silver must convert); `TIMESTAMPTZ` -> `TIMESTAMP` |
| `lb_program_setting_change_history` | exists with 0 rows (empty source table) |

## App-side join in Postgres

The app's query pattern (synced worklist LEFT JOIN its own outreach rows, same database) runs in Postgres.
Reached / assigned for the last worklist days: 10-30 29/42, 10-31 32/50, 11-01 18/40, 11-02 27/50,
11-03 27/50, 11-04 16/50 (partial, cut off at 11-05 release), 11-05 0/46.

## Daily cycle with publish (`dev_readmit_daily_cycle`, DECISIONS.md #41)

| Run | Result |
|---|---|
| 698272390898411 | Cancelled by the author's build after about 15 min: `publish_worklist` never started a sync. Bug: the busy-pipeline wait compared `latest_updates[].state` (`UpdateStateInfoState`) with `UpdateInfoState` members, which never match. Fixed by comparing values; regression test `test_publish_state_check_handles_both_pipeline_enums` |
| Rerun | All four tasks succeeded. `publish_worklist`: `care_worklist_synced` update cfe40550 COMPLETED, UC 46 = Postgres 46 rows for 2026-11-05; `care_team_roster_synced` update 99498415 COMPLETED, UC 5 = Postgres 5 |
