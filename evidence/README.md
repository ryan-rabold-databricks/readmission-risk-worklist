# Evidence index

Committed text output of every run that backs a claim in [`README.md`](../README.md) and
[`docs/DECISIONS.md`](../docs/DECISIONS.md). All data is synthetic. Workspace `fevm-classic-stable`, catalog
`rtr_demo_catalog`, Lakebase project `readmission-worklist`.

Evidence files are historical records and are not edited after the fact. When a later decision changed the
data or the design, the file is marked **superseded** below and points to the current evidence.

**Status key:** **Current** = matches the deployed state today. **Superseded** = true when captured, replaced
by later data or a later decision (see the note). **Failure record** = a failed run kept on purpose because a
decision cites it. **Corrected** = the file contains a statement found wrong later (see the note).

## Data lineage of the evidence

The numbers change at two points, so compare numbers only within one era:

| Era | Dates | Data | Files |
|---|---|---|---|
| v2 | 2026-11-02 to 11-03 | Simulator generator v2 | `phase1/`, `phase2/` |
| v3 | 2026-11-05 | Generator v3 (#35), models v3-v9 | `phase3/`, `phase4/` files dated 11-05 |
| **v4 (current)** | 2026-11-06 onward | Generator v4 program response (#45), re-landed and rebuilt; models v10-v16 | `phase4/` files dated 11-06, `phase5/`, `phase6/`, `phase7/` |

On 2026-11-13 the data was refreshed (`phase7/refresh_*`): new extract days through 2026-11-12, worklist days
2026-11-07 to 2026-11-13, simulated outreach for days before 2026-11-13 (2026-11-13 is left open for a live demo),
and a pipeline update. Numbers in files before the refresh stop at worklist day 2026-11-06; the current Program
numbers are in `phase7/refresh_6_program_numbers.raw.txt`.

**Redaction window (#60):** from 2026-11-04 12:54 UTC to the repair on 2026-11-08, patient names in
`clinical_silver.patient` and `care_worklist` were physically "REDACTED". Checks run in that window that compare
against names prove nothing; both have been re-run in `phase7/c1_phi_content_checks.raw.txt`.

## Files by phase

### Phase 1: source simulator (v2 data)

| File | Backs | Status |
|---|---|---|
| `phase1/simulator_job_runs.log` | #19, #20 (rerun "nothing to do") | Superseded (B1): v2 story numbers; current v4 numbers in `phase4/simulator_v4_reland.log` |
| `phase1/landing_validation.md` | Landing volume, injected bad rows, referential integrity | Superseded (B1): v2 counts; the checks are unchanged in kind |

### Phase 2: Lakeflow SDP pipeline (v2 data)

| File | Backs | Status |
|---|---|---|
| `phase2/pipeline_run.md` | #22, #24 (updates 2ea751, 56feb0), #25 (b789d7, 896b85) | Current for the decisions it backs (pipeline behavior), v2 row counts |
| `phase2/data_validation.md` | Bronze = landed, quarantine precision, AUTO CDC, PKs, #23, #26 | Superseded (B1): v2 counts and rates; the v4 equivalents are `phase4/v4_data_checks.raw.txt` and `phase5/outcome_validation.raw.txt` |
| `phase2/simulator_reland.log` | #22 (v1 volume dropped and re-landed) | Current (historical step) |

### Phase 3: model, scoring, worklist (v3 data)

| File | Backs | Status |
|---|---|---|
| `phase3/model_signal_diagnosis.md`, `feature_experiment.py`, `simulator_auc_estimator.py` | #35 (AUC gate failure, simulator fix) | Current (historical diagnosis) |
| `phase3/program_backfill.log` | #29, #30, #39 (runs 115414619554499, 560385146091070) | Superseded (B2) by `phase4/program_backfill_v4.log` for model versions; current for the #39 failures |
| `phase3/daily_cycle_runs.log` | #39 (empty briefs at max_tokens 300, then 691 briefs) | Current (historical step) |
| `phase3/worklist_validation.md` | #31-#33: coverage, idempotency, capacity, highest-risk-first, brief coverage, calibration | Superseded (B2): v3 models v3-v9 and counts (8,802 items); current models in `phase7/cli_checks.txt` (C6). Its "no PHI in briefs" check ran inside the redaction window and is **replaced** by `phase7/c1_phi_content_checks.raw.txt` |

### Phase 4: Lakebase, CDF, outreach, v4 rebuild

| File | Backs | Status |
|---|---|---|
| `phase4/lakebase_validation.md` | #40-#44 | Superseded (B3): 8,802 synced rows / 24 columns became 1,465 / 13 (#46); synced storage moved (#48). Provisioning, CDF, and idempotency findings still hold |
| `phase4/setup_run_1.log` | #43 (invalid CDF config ID) | Failure record |
| `phase4/setup_run_2.log`, `setup_run_3_rerun.log` | #4, #42, #43 (REPLICA IDENTITY FULL, idempotent) | Current |
| `phase4/postgres_validation.raw.txt` | #42 | Superseded (B3) for row counts and columns; current for schemas and replica identity |
| `phase4/cdf_landing_validation.raw.txt` | #43 (UUID lands as BINARY; landing timestamps within seconds of the writes) | Current for the CDF facts; the gold table list predates #48 |
| `phase4/daily_cycle_with_publish.log` | #41 | Superseded by `daily_cycle_v4.log` (#46 counts) |
| `phase4/outreach_sim_run_1.log`, `outreach_sim_run_2_rerun.log` | #44 (idempotent insert) | Superseded by `outreach_sim_v4_reconcile.log` for counts; current for idempotency |
| `phase4/v4_rebuild_validation.md` | #45-#48 | **Corrected (B4):** its last row says `readmission_worklist_gold` holds "only data-product objects". The #48 correction (2026-11-09) found the two `event_log_*` tables belong to the live sync pipelines and stay there; see `phase7/c2_c5_governance_checks.raw.txt` (C5) and `phase7/cli_checks.txt`. All other rows current |
| `phase4/simulator_v4_dry_run.txt`, `simulator_v4_reland.log` | #45; current simulator story numbers (README) | Current |
| `phase4/simulator_v4_reland_attempt1_timeout.log` | #45 rebuild step 2 | Failure record |
| `phase4/rebuild_reset.log`, `pipeline_full_refresh_v4.log`, `program_backfill_v4.log`, `outreach_sim_v4_reconcile.log`, `daily_cycle_v4.log`, `publish_snapshot_test.log` | #45, #46 rebuild steps | Current |
| `phase4/v4_data_checks.raw.txt` | #47 (0 leaked features), program vs prior year | Current |
| `phase4/v4_program_effect.raw.txt`, `v4_rebuild_consistency.raw.txt` | #45 | Current (REACHED-only definition; #53 widens "reached", see `phase5/outcome_validation.raw.txt`) |

### Phase 5: app, write-back, telemetry

| File | Backs | Status |
|---|---|---|
| `phase5/app_validation.md` | #50-#57 | **Superseded in part (B5):** the Program tab capture shows 7-day follow-up 49.7% / +2.7 pts, changed by #59 to 50.8% / +3.9 (current values in `phase6/app_validation.md` and `phase7/c7_program_numbers.raw.txt`). **Unsupported as captured, re-tested (#54):** its out-of-roster 404, invalid `activity_type` 400, outreach retry 200, and pre-group 403 do not appear in the deployed app's request logs (0 4xx responses through 2026-11-10, `phase7/c10_b6_app_telemetry.raw.txt`). All four were re-run on the deployed app on 2026-11-13 and confirmed server-side (`phase7/app_checks_console.txt`, `phase7/app_checks_request_logs.raw.txt`). Settings 201 + idempotent 200, outreach 201, `/api/me`, and the 39-item worklist scope were already confirmed |
| `phase5/audit_event_validation.raw.txt` | #55 | Current for event counts and joins. Its "PHI scan: 0 hits" ran inside the redaction window and is **replaced** by `phase7/c1_phi_content_checks.raw.txt` |
| `phase5/outcome_validation.raw.txt` | #52, #53 | Current |
| `phase5/settings_validation.raw.txt`, `settings_validation_insert.log`, `pipeline_run_3_settings.log` | #51 | Current |
| `phase5/pipeline_run_1.log` to `_5_app_settings.log` | #50-#53, #55 (updates 2b9e94, 36b2df, 9e6367) | Current |
| `phase5/daily_cycle_after_settings.log` | #51 (effective-dated policy in the cycle) | Current |
| `phase5/setup_app_grants.log` | #42, #55 (Postgres and UC grants for the app SP) | Current |
| `phase5/app_deploy_1.log`, `_2.log` | #56 (lockfile proxy, build-time typegen) | Failure record |
| `phase5/app_deploy_3.log` to `_7.log` | #56 | Current |

### Phase 6: governance, metric view, Genie

| File | Backs | Status |
|---|---|---|
| `phase6/redaction_repair_1_tags.log` to `_4_publish.log`, `redaction_repair_3_worklist.sql` | #60 repair | Current. Root cause (who tagged what, when) is in `phase7/c2_c5_governance_checks.raw.txt` (C3) |
| `phase6/governance_run_1.log` | #62 (tag policy limit) | Failure record |
| `phase6/governance_run_2.log` to `_6_synced_tags.log` | #62, #65, #66 (25 tags, 3 functions, 12 policies, idempotent; leader grants skipped for the workspace-local group) | Current |
| `phase6/abac_sp_check.py` | Test-SP check script (mints a secret; author runs it) | Current |
| `phase6/abac_validation_sp_1.raw.txt` | #65 defect 1 (no USE SCHEMA, every query refused) | Failure record |
| `phase6/abac_validation_sp_2.raw.txt` | #66 defect 3 (synced foreign table leaked 1,465 real names) | Failure record |
| `phase6/abac_validation_sp_3.raw.txt`, `_4.raw.txt` | #62, #65, #66 (all pass) | Current |
| `phase6/classification_off_check.txt` | #64 | Current |
| `phase6/metric_view_*.txt`, `metric_view_target_program_kpis.json` | #61 | Current; re-confirmed unchanged in `phase7/c7_program_numbers.raw.txt` |
| `phase6/genie_validation.txt`, `genie_example_sql_validation.txt` | #63 | Current. Note: asked "Which facility has the highest readmission rate compared with last year?", Genie ranked by current rate (Riverbend) and said so; a question about the largest year-over-year change needs that wording |
| `phase6/genie_audit_event.raw.txt` | #63 (`genie.asked` emitted, IDs only) | Current |
| `phase6/genie_in_app_after_resignin.txt` | #63 in-app Genie after re-sign-in | Current for the two 200 responses and two audit events. **Its `action` / `record_type` = None is a query artifact (B6):** that query read the record's top-level `event_name` column, which is empty for these records; the event name and fields are in `attributes`. Stored values: `new_conversation`, then `follow_up` with the conversation ID (`phase7/c10_b6_app_telemetry.raw.txt`) |
| `phase6/app_validation.md`, `app_deploy_1.log` | #59, #61, #63 | Current |
| `phase6/publish_regrant_run.log` | #68 | Current |

### Phase 7: evidence pass (2026-11-10)

Re-runnable: SQL checks run with `python3 evidence/phase7/run_sql.py evidence/phase7/<name>.sql` (writes
`<name>.raw.txt`); CLI checks with `bash evidence/phase7/cli_checks.sh > evidence/phase7/cli_checks.txt 2>&1`.
All read-only except C11, which runs in a rolled-back transaction.

| File | Check | Result |
|---|---|---|
| `c1_phi_content_checks.raw.txt` | C1: PHI in briefs and telemetry, against real names (#31, #55) | Names real (69,126 patients, 0 redacted). 672 briefs: 0 contain the patient's first name, last name, MRN, or phone digits; 0 contain any worklist patient's full name. 1,001 telemetry records: 0 name, MRN, phone, or SQL-text hits. Positive controls: the same matching finds 8,640 / 8,640 names in their own rows, and the user's email in 20 telemetry records |
| `c2_c5_governance_checks.raw.txt` | C2: exempt identity (#62) | Author reads 0 masked values in bronze, silver, `care_worklist`, its view, and the synced foreign table, and all 5 facilities. **Not yet proven: the write path under the policies.** The first `readmit_*` policy write is 2026-11-09 02:05 UTC; the latest pipeline and job writes are 2026-11-06 to 11-08, so no refresh has run since the masks existed |
| same | C3: root cause of #60 | 2026-11-04 12:54 UTC: the workspace's **DataClassification Service Principal** (`77f19abf-…`, identified in `cli_checks.txt`) added `class.name` to `first_name` / `last_name` in `clinical_silver.patient` and `ehr_bronze.patient_raw`. A **fifth** assignment, not in #60, hit `care_worklist_synced.patient_display_name` on 2026-11-06 12:54; that table was recreated at 16:20 the same day (#48), so the tag went with it, and its current tags are only `phi_data_classification` / `row_filter_policy` |
| same | C4: leadership test (#65) | Author: `is_member` true, `is_account_group_member` false; the facility filter returns all 5 facilities |
| same | C5: #67 | `care_team_assignment`: 1 care manager, 5 active rows, all 5 facilities. Two `event_log_*` tables in gold, last altered 2026-11-10 |
| `cli_checks.txt` | C2-C6 via CLI | Policy definitions on all four schemas: `to` account users, `except` the author only. DataClassification SP identity. Account API refused ("disabled for users without account admin status", #65). `care_mgmt_leadership` is a WorkspaceGroup with the author as its member. Sync pipelines 2051653d / 79bc3344 write to `readmission_worklist_gold`. Model: `@champion` = `@challenger` = v16 (as of 2026-11-01), test AUC 0.745, Brier 0.111, calibration slope 1.00, promoted |
| `c7_program_numbers.raw.txt` | C7: Program tab numbers from the app's own queries, before the refresh (superseded by `refresh_6_program_numbers.raw.txt`) | Equal to `phase6/metric_view_headline.txt`: readmission 14.36% vs 14.99% prior year, follow-up 50.8% vs 46.9%, reach 64.3%, cost avoided $2,641,204 (176) / $2,201,449 (147) |
| `c8_unit_tests.txt` | C8: unit tests | pytest 72 passed, 3 skipped (local machine has no XGBoost library or Java for local Spark); vitest 6 passed |
| `c9_bundle_validate_plan.txt` | C9: bundle | Validation OK. Plan: 0 add, 9 change, 0 delete, 18 unchanged. Changes: 7 jobs (per-deploy wheel path, #28); app `config.env` (values read back as null, old = new); Genie space permissions (the app service principal holds CAN_RUN remotely, not declared in the bundle). The Genie space's remote `serialized_space` differs from the bundle's (plan action `skip`) |
| `c10_b6_app_telemetry.raw.txt` | C10: #54 access-scope responses; B6 | See Phase 5 and Phase 6 notes above. Also: `care_management_silver.app_audit_event` lags bronze (3 `genie.asked` and 4 `worklist.viewed` records since 2026-11-09 are not curated yet) because the pipeline has not run since 2026-11-07 |
| `refresh_1_source_simulator.log`, `refresh_2_daily_cycle.log` | Data refresh (2026-11-13) | 7 extract dates landed (plus 17 late-arriving records); worklist days 2026-11-07..13 scored with v16 and built, 325 briefs, 0 errors; publish UC = Postgres 1,422 / 50 rows, app read grants re-applied |
| `refresh_3_write_path_check.raw.txt` | #62 write path under the project's policies | 187 silver patient rows and 325 worklist rows written after the policies existed, 0 masked or redacted, in UC and in the Lakebase copy; 28 project tags intact, 0 `class.*`; silver audit events caught up with bronze |
| `refresh_4_outreach_simulator.log`, `refresh_5_pipeline.log` | Outreach for the new days, then pipeline update 6bf73f | 765 simulated calls inserted, 0 stale deleted, reach rate 0.598 |
| `refresh_6_program_numbers.raw.txt` | **Current Program numbers (deck)** | Latest worklist day 2026-11-13. Readmission 14.43% vs 15.02% prior year; 7-day follow-up 50.8% vs 47.0%; reach 64.4%; cost avoided $2,628,272 (175 readmissions, within tier) and $2,208,028 (147, vs prior year); 8,965 items, 366 overflow. Silver outreach = CDF current state (21,568) |
| `app_checks_console.txt`, `app_checks_request_logs.raw.txt` | #54 app access checks on the deployed app (2026-11-13) | Out-of-scope item: 404 on read and on write, no row written. Invalid `activity_type`: 400. Retried `client_request_id`: 201 then 200, same `activity_id`, one CDF row. Author removed from `care_mgmt_leadership`: `isLeader` false, 403 on Program Settings read and write, no change written. Every status matched in the app's request logs; only the 201 emitted `outreach.logged` |
| `c11_lakebase_privilege_check.txt` | C11: #68 | Synced tables owned by `databricks_writer_16845`. Refused: `ALTER DEFAULT PRIVILEGES FOR ROLE` ("permission denied to change default privileges") and `GRANT databricks_reader_16845` ("Only roles with the ADMIN option … may grant this role"). App role can SELECT both synced tables today. Rolled back |

## Decision to evidence map

| # | Evidence | Note |
|---|---|---|
| 1, 2, 7, 10, 11, 14, 49 | None needed | Scope and naming decisions |
| 3, 4 | `phase4/setup_run_2.log`, `cdf_landing_validation.raw.txt`, `postgres_validation.raw.txt` | |
| 5, 6 | Not captured as command output | Effect of #6 visible in `phase6/abac_validation_sp_2.raw.txt` (synced table readable by account users) |
| 12, 13 | `phase5/audit_event_validation.raw.txt`, `phase7/c10_b6_app_telemetry.raw.txt`, `phase7/c1_phi_content_checks.raw.txt` | |
| 15, 30 | `phase4/program_backfill_v4.log`, `phase7/cli_checks.txt` (C6) | |
| 16, 21 | Not captured | Observations described in the decision text only |
| 17, 28 | `phase7/c9_bundle_validate_plan.txt` (wheel build, versioned wheel path) | |
| 18 | `tests/test_env_guardrail.py`, `phase7/c8_unit_tests.txt` | |
| 19, 20 | `phase1/simulator_job_runs.log` (v2), `phase4/simulator_v4_reland.log` (current) | |
| 22, 24, 25 | `phase2/pipeline_run.md`, `phase2/simulator_reland.log` | |
| 23, 26 | `phase2/data_validation.md` (v2) | |
| 27 | `seeds/` | Corrected 2026-11-10 (capacity 50, #32) |
| 29 | `phase3/program_backfill.log`, `phase4/program_backfill_v4.log` | |
| 31 | `phase3/worklist_validation.md` (coverage), `phase7/c1_phi_content_checks.raw.txt` (PHI) | |
| 32, 33 | `phase3/worklist_validation.md` (v3), `phase5/settings_validation.raw.txt` | |
| 34 | `phase3/program_backfill.log` | The tag-limit failure is described in the decision only |
| 35 | `phase3/model_signal_diagnosis.md`, `phase4/v4_rebuild_validation.md` (v10 = 0.7498) | |
| 36 | Not captured | Update 4f60f1 cited, no log committed |
| 37 | `phase7/c9_bundle_validate_plan.txt` (warehouse unchanged in plan) | |
| 38 | docs.databricks.com compliance page (cited in the decision) | Documentation, not a run |
| 39 | `phase3/daily_cycle_runs.log`, `phase3/program_backfill.log` | |
| 40-44 | `phase4/` (see table) | #41 storage superseded by #48 |
| 45-48 | `phase4/v4_*`, `daily_cycle_v4.log`, `publish_snapshot_test.log`; #48 correction in `phase7/c2_c5_governance_checks.raw.txt`, `phase7/cli_checks.txt` | |
| 50-53 | `phase5/pipeline_run_*.log`, `outcome_validation.raw.txt`, `settings_validation.raw.txt` | |
| 54 | `phase5/app_validation.md`, `phase7/c10_b6_app_telemetry.raw.txt`, `phase7/app_checks_console.txt`, `phase7/app_checks_request_logs.raw.txt` | 404 / 400 / outreach retry / 403 re-tested 2026-11-13 |
| 55 | `phase5/audit_event_validation.raw.txt`, `phase7/c1_phi_content_checks.raw.txt` | |
| 56 | `phase5/app_deploy_*.log` | |
| 57-59 | `phase6/app_validation.md`, `phase6/metric_view_*`, `phase7/c7_program_numbers.raw.txt` | `phase5/app_validation.md` shows pre-#59 values |
| 60 | `phase6/redaction_repair_*`, `phase7/c2_c5_governance_checks.raw.txt` (C3), `phase7/cli_checks.txt` | Fifth tag found in Phase 7 |
| 61 | `phase6/metric_view_*`, `phase7/c7_program_numbers.raw.txt` | |
| 62 | `phase6/governance_run_*`, `abac_validation_sp_3/_4`, `phase7/cli_checks.txt`, `phase7/c2_c5_governance_checks.raw.txt`, `phase7/refresh_3_write_path_check.raw.txt` | Write path under the policies proven 2026-11-13 |
| 63 | `phase6/genie_*`, `phase7/c10_b6_app_telemetry.raw.txt` | |
| 64 | `phase6/classification_off_check.txt` | |
| 65 | `phase6/abac_validation_sp_1` / `_3`, `phase7/c2_c5_governance_checks.raw.txt` (C4), `phase7/cli_checks.txt` | |
| 66 | `phase6/abac_validation_sp_2` / `_3` / `_4`, `governance_run_6_synced_tags.log` | |
| 67 | `phase7/c2_c5_governance_checks.raw.txt` (C5), `phase7/cli_checks.txt` | (a) prod deploy as the SP: never run, no prod workspace |
| 68 | `phase6/publish_regrant_run.log`, `phase7/c11_lakebase_privilege_check.txt` | |

## Known gaps (not closed by evidence)

- The facility filter's assigned-subset branch is untested end to end: one care manager, assigned to all five facilities (#67).
- Prod deployment as the service principal has never run (#67).
- The app's out-of-scope check (#54) uses an item aged out of the synced window; an other-facility item needs a second care manager (#67).
- `readmission_outcome` refreshes in `ingest_curate`, before `build_worklist`, so the Program tab and Genie trail the newest worklist day by one daily cycle.
- Open items in DECISIONS.md: telemetry delivery semantics through Zerobus, SDP foreign keys.
