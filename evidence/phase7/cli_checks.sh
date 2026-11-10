#!/usr/bin/env bash
# CLI evidence for C2-C6 (read-only). Usage: bash evidence/phase7/cli_checks.sh > evidence/phase7/cli_checks.txt 2>&1
set -u
P=(--profile fevm-classic-stable)
MODEL=rtr_demo_catalog.readmission_worklist_gold.readmission_risk
run() { echo "\$ $*"; "$@"; echo "(exit $?)"; echo; }

echo "# Phase 7 CLI checks, run $(date -u +%Y-%m-%dT%H:%M:%SZ) as $(databricks current-user me "${P[@]}" -o json | jq -r .userName)"
echo

echo "## C2: ABAC policies on each masked schema (to_principals, except_principals, function)"
for s in ehr_bronze clinical_silver care_management_silver readmission_worklist_gold; do
  echo "\$ databricks policies list-policies schema rtr_demo_catalog.$s"
  databricks policies list-policies schema "rtr_demo_catalog.$s" "${P[@]}" -o json \
    | jq -c '.[] | {name, for_securable_type, to_principals, except_principals, mask: .column_mask.function_name, filter: .row_filter.function_name, match: [.match_columns[]?.condition]}'
  echo
done

echo "## C3: identity of the principal that added class.name to the patient name columns (#60)"
run databricks service-principals list "${P[@]}" --filter 'applicationId eq "77f19abf-81ef-4969-ad97-cc0e63a8f662"' -o json

echo "## C4: account-level group lookup as the author (#65: not an account admin)"
run databricks account groups list --profile fevm-account --filter 'displayName eq "care_mgmt_leadership"'
GID=$(databricks groups list "${P[@]}" --filter 'displayName eq "care_mgmt_leadership"' -o json | jq -r '.[0].id')
echo "\$ databricks groups get $GID  (workspace-local group care_mgmt_leadership; list omits members)"
databricks groups get "$GID" "${P[@]}" -o json | jq -c '{id, displayName, members: [.members[]? | .display], meta}'
echo

echo "## C5: the two synced-table pipelines whose event_log_* tables stay in readmission_worklist_gold (#48 correction, #67)"
for id in 2051653d-2e68-439e-95ae-74fcd727038d 79bc3344-3bf2-41d7-85c0-9b6215af1a2e; do
  echo "\$ databricks pipelines get $id"
  databricks pipelines get "$id" "${P[@]}" -o json \
    | jq -c '{pipeline_id, name, state, spec_catalog: .spec.catalog, spec_schema: .spec.schema, latest_update: (.latest_updates[0] | {update_id, state, creation_time})}'
  echo
done

echo "## C6: model aliases and the champion version"
echo "\$ databricks registered-models get $MODEL --include-aliases"
databricks registered-models get "$MODEL" --include-aliases "${P[@]}" -o json | jq -c '{full_name, aliases}'
echo
CHAMP=$(databricks registered-models get "$MODEL" --include-aliases "${P[@]}" -o json | jq -r '.aliases[] | select(.alias_name=="champion") | .version_num')
echo "\$ databricks model-versions get $MODEL $CHAMP"
databricks model-versions get "$MODEL" "$CHAMP" "${P[@]}" -o json | jq -c '{version, run_id, status, created_at, created_by}'
RUN=$(databricks model-versions get "$MODEL" "$CHAMP" "${P[@]}" -o json | jq -r .run_id)
echo
echo "\$ databricks experiments get-run $RUN  (metrics, params, tags)"
databricks experiments get-run "$RUN" "${P[@]}" -o json \
  | jq '{run_id: .run.info.run_id, run_name: .run.info.run_name, status: .run.info.status,
         metrics: ([.run.data.metrics[]? | {(.key): .value}] | add),
         params: ([.run.data.params[]? | {(.key): .value}] | add),
         tags: ([.run.data.tags[]? | select(.key | startswith("mlflow.") | not) | {(.key): (.value | tostring | .[0:200])}] | add)}'
echo
echo "\$ databricks model-versions get $MODEL <v>  for v in 10..30 (versions from the v4 rebuild, #45)"
for v in $(seq 10 30); do
  out=$(databricks model-versions get "$MODEL" "$v" "${P[@]}" -o json 2>/dev/null) || continue
  echo "$out" | jq -c '{version, status, created_at, run_id}'
done
