# Phase 5 validation: AppKit app, write-back, telemetry, audit events

Workspace `fevm-classic-stable`, catalog `rtr_demo_catalog`, app `dev-readmission-worklist`
(AppKit 0.76.1), runs 2026-11-06/07. All data synthetic. Raw outputs sit next to this file.

## 5a. Pipeline pieces the app depends on

| Check | Result | Raw output |
|---|---|---|
| `care_management_silver.outreach_activity` = current state of the CDF history | 20,800 = 20,800 rows; 0 malformed UUIDs; one `activity_id` found in Postgres with the same `client_request_id` | `outcome_validation.raw.txt` |
| `readmission_outcome` grain | 113,711 rows = 113,711 discharges; 0 readmissions without `readmit_encounter_id`, 0 the other way | `outcome_validation.raw.txt` |
| Program effect from `readmission_outcome` | HIGH reached 35.1% vs not reached 38.7% readmitted (predicted 39.4% vs 39.3%); MEDIUM 18.5% vs 23.0% | `outcome_validation.raw.txt` |
| Settings validation in the pipeline | Tier change with a gap REJECTED ("MEDIUM max_score must equal HIGH min_score"); capacity change APPLIED as a new effective-dated version | `settings_validation.raw.txt` |
| Daily cycle with effective-dated tier policy | `ingest_curate`, `score_discharges`, `build_worklist`, `publish_worklist` all SUCCESS | `daily_cycle_after_settings.log` |
| Unit tests | Python 58 passed (incl. `tests/test_program_settings.py`); app vitest 6 passed (`server/settings-validation.test.ts`) | - |

## 5b. Deployed app

| Check | Result |
|---|---|
| Deploy | `bundle run readmission_worklist_app`: RUNNING, deployment SUCCEEDED (`app_deploy_5.log`). Earlier failures fixed: lockfile pointed one package at an internal npm proxy (`app_deploy_1.log`); build-time typegen ran as the service principal without UC access (`app_deploy_2.log`) |
| Setup grants | `readmit_setup --params app_role=<app SP>`: Postgres SELECT on the synced schema, SELECT/INSERT on the app schema; UC USE_SCHEMA/CREATE_TABLE/SELECT/MODIFY on `readmission_worklist_app_bronze` (`setup_app_grants.log`) |
| Worklist scope | Signed-in care manager sees 39 items for 2026-11-06 at their rostered facilities; an item outside the roster returns 404 |
| Outreach write | Logged LEFT_VOICEMAIL from the item drawer: 201; retry with the same `client_request_id` returns the same row (200); invalid `activity_type` 400 |
| Leadership gate | `/api/me` `isLeader` from the user's own SCIM `/Me` (group `care_mgmt_leadership`); before the group existed, Program Settings API returned 403 |
| Program tab (on behalf of the user) | KPIs, trend, facility and tier tables render from `readmission_outcome` (text capture below) |
| Settings change from the deployed app | Capacity change `4d2bdda6-...`: 201, retry 200 same `change_id`; CDF landed it; pipeline update 9e6367 APPLIED it as a version from 2026-11-09 (`audit_event_validation.raw.txt`) |
| App telemetry | `app_otel_logs`, `app_otel_metrics`, `app_otel_traces` created by the platform (plus `app_otel_annotations`); app stdout/stderr also lands in `app_otel_logs` |
| Audit events | 7 audit records in bronze = 7 rows in `care_management_silver.app_audit_event`; `worklist.viewed`, `outreach.logged`, `settings.changed` all present with trace IDs; the `outreach.logged` record ID joins to silver `outreach_activity` |
| No PHI in telemetry | 0 records in `app_otel_logs` matching phone patterns, SQL text, or patient-name columns (`audit_event_validation.raw.txt`) |

## Deployed UI text capture (2026-11-07)

Program tab:

```
30-day readmission rate 14.4%   Prior year 15.0%. -0.6 pts vs prior year
Reach rate 64.3%                8,640 items, 358 overflow. Median first contact 22 h after release.
7-day follow-up rate 49.7%      Prior year 46.9%. +2.7 pts vs prior year
Estimated cost avoided $2,641,204   176 readmissions avoided x $15,000 (within-tier reached vs not reached; an estimate)

Facility                         Readmit  Prior year  7-day f/u  Reach   Overflow
Riverbend Community Hospital     19.4%    20.5%       31.1%      62.4%   41
Cedar Creek Community Hospital   14.2%    15.2%       49.7%      63.8%   40
Southview Hospital               14.0%    15.2%       48.9%      64.6%   70
Northgate Regional Hospital      13.9%    14.1%       51.7%      63.1%   79
Lakeside Medical Center          13.4%    13.7%       54.5%      65.0%   128
```

Program Settings change log:

```
Nov 7, 11:51 AM  Daily capacity  ryan.rabold@databricks.com  2026-11-09  APPLIED
Nov 6, 5:23 PM   Daily capacity  ryan.rabold@databricks.com  2026-11-08  APPLIED
Nov 6, 5:23 PM   Risk tiers      ALL                         2026-11-08  REJECTED  MEDIUM max_score must equal HIGH min_score
```

Worklist (2026-11-06; names and phones omitted here): 39 assigned, 39 open, 19 overdue. Top row:
`HIGH 60% | FAC-CCH | Attempt 2, left voicemail` (the two validation calls). This day is after the outreach
simulator's `run_date`, so the remaining items are not started.
