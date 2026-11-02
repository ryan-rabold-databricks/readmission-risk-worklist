# Project context for AI assistants

FE Bar submission: Readmission Prevention Worklist on Databricks. Read `README.md`, `docs/DECISIONS.md`, and `docs/readmission-worklist-high-level-design.pdf` before building. The design (v0.4) is approved; do not change architecture without asking the author.

## Environment

- Workspace profile: `fevm-classic-stable`
- Dev catalog: `rtr_demo_catalog` (existing; do not create or alter catalog-level grants)
- Lakebase project `readmission-worklist`, database `readmission_worklist`
- LLM endpoint for `ai_query`: bundle variable `llm_endpoint` (default `databricks-claude-opus-5-5`)

## Naming (see DECISIONS.md #7-#10)

`ehr_raw`, `ehr_bronze`, `clinical_silver`, `care_management_silver`, `readmission_worklist_gold`, `readmission_worklist_app_bronze`, `phi_governance`. Lakebase Postgres schemas: `readmission_worklist_gold` (synced, `_synced` suffix, read-only), `readmission_worklist_app` (app writes, `REPLICA IDENTITY FULL`). Never start a CDF feed on the `readmission_worklist_gold` Postgres schema.

## Build phases

1. Bundle skeleton (`databricks.yml`, dev/prod targets, variables), schemas and volume, synthetic EHR source simulator
2. Lakeflow SDP pipeline: ehr_bronze to clinical_silver / care_management_silver to readmission_worklist_gold features and labels
3. Model training with `@champion`, daily scoring, worklist build with `ai_query` briefs
4. Lakebase project, synced tables, app schema, Lakebase CDF feed (setup job, idempotent)
5. AppKit app: Worklist, Program, Program Settings tabs; app telemetry and audit events
6. Genie Agent, metric view, ABAC policies and PHI tags
7. Evidence pass, deck, roleplay prep

## Rules

- Synthetic data only. No PHI in telemetry, only IDs.
- FE Bar evaluator reads text only: commit run outputs (notebook outputs, logs, query results) to `evidence/`.
- Commit at milestones; end commit messages with `Co-authored-by: Isaac <no-reply@databricks.com>`.
- Verify Databricks features against docs.databricks.com; the bundled skill references have been out of date on Lakebase.
