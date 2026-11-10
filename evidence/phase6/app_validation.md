# Phase 6 app validation (2026-11-08, deployed dev-readmission-worklist, signed in as the author)

Deploy: `bundle deploy` then `bundle run readmission_worklist_app` (`app_deploy_1.log`).
App config: `user_api_scopes` = sql, genie; effective scopes add iam.current-user:read and
iam.access-control:read; resources sql-warehouse, postgres, genie-space.

| Check | Result |
|---|---|
| Worklist names after the redaction repair (#60) | Real names on 2026-11-06 (39 assigned, 20 overdue); no "REDACTED" |
| Program tab reads the metric view | Source line names `readmission_worklist_gold.readmission_program_metrics` |
| KPI cards equal the pre-change values | 14.4% vs 15.0% readmit; reach 64.3%; follow-up 50.8% vs 46.9% (+3.9 pts); cost avoided $2,641,204 (176) and cross-check $2,201,449 (147); 8,640 items, 358 overflow, median first contact 22 h |
| Facility table uses the KPI reach definition (#61) | Riverbend 62.6%, Cedar Creek 64.2%, Southview 64.8%, Northgate 63.3%, Lakeside 65.3% (each +0.3 pts vs before) |
| Genie panel shown to leaders | "Ask about the program" card with GenieChat |
| Genie answer in the app | FAILED for the existing session: "Provided OAuth token does not have required scopes: genie". The session token predates the scope added in this deploy; needs a fresh sign-in (consent) |
| Genie answer in the app after a fresh sign-in (2026-11-10) | PASSED: two questions, both `POST /api/genie/default/messages` 200, each with an `audit.genie.asked` event; no scope errors (`genie_in_app_after_resignin.txt`) |
| `genie.asked` audit event | Emitted server-side for that question: `audit.genie.asked`, action new_conversation, record_type genie_conversation, IDs only (`genie_audit_event.raw.txt`) |
| Genie through the Conversation API (author) | Matches the tab (`genie_validation.txt`) |
