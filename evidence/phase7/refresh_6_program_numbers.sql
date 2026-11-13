# Refresh 6: Program tab numbers after the 2026-11-13 refresh (worklist days to 2026-11-13, outreach simulated before
# 2026-11-13, pipeline update 6bf73f). These are the numbers for the deck. Previously C7, from the app's own *.obo.sql queries (parameters bound to the dev defaults:
# catalog = rtr_demo_catalog, go_live = 2026-05-01). Data unchanged since worklist day 2026-11-06 (D1 not run),
# so these should equal evidence/phase6/metric_view_headline.txt and app_validation.md. Run as the author (exempt).
-- ### program_kpis.obo.sql
SELECT
  MEASURE(program_start) AS program_start,
  MEASURE(matured_through) AS matured_through,
  MEASURE(data_through) AS data_through,
  MEASURE(latest_worklist_date) AS latest_worklist_date,
  MEASURE(program_discharges) AS program_discharges,
  MEASURE(program_readmission_rate) AS program_readmit_rate,
  MEASURE(baseline_readmission_rate) AS baseline_readmit_rate,
  MEASURE(program_followup_7d_rate) AS program_followup_7d_rate,
  MEASURE(baseline_followup_7d_rate) AS baseline_followup_7d_rate,
  MEASURE(reach_rate) AS reach_rate,
  MEASURE(worklist_items) AS worklist_items,
  MEASURE(overflow_items) AS overflow_items,
  MEASURE(median_first_contact_hours) AS median_first_contact_hours,
  MEASURE(readmissions_avoided) AS readmissions_avoided,
  MEASURE(est_cost_avoided) AS est_cost_avoided,
  MEASURE(matured_program_discharges) AS matured_program_discharges,
  MEASURE(readmissions_avoided_vs_prior_year) AS readmissions_avoided_yoy,
  MEASURE(est_cost_avoided_vs_prior_year) AS est_cost_avoided_yoy
FROM rtr_demo_catalog.readmission_worklist_gold.readmission_program_metrics
-- ### program_by_facility.obo.sql
SELECT
  facility_id,
  facility_name,
  MEASURE(program_discharges) AS program_discharges,
  MEASURE(program_readmission_rate) AS program_readmit_rate,
  MEASURE(baseline_readmission_rate) AS baseline_readmit_rate,
  MEASURE(program_followup_7d_rate) AS program_followup_7d_rate,
  MEASURE(reach_rate) AS reach_rate,
  MEASURE(overflow_items) AS overflow_items
FROM rtr_demo_catalog.readmission_worklist_gold.readmission_program_metrics
WHERE period IS NOT NULL
GROUP BY facility_id, facility_name
ORDER BY program_readmit_rate DESC
-- ### program_effect_by_tier.obo.sql
SELECT
  risk_tier,
  CASE WHEN assignment_status = 'OVERFLOW' THEN 'Overflow (not worked)'
       WHEN was_reached THEN 'Reached'
       ELSE 'Assigned, not reached' END AS outreach_group,
  count(*) AS items,
  avg(cast(readmitted_30d AS INT)) AS readmit_rate,
  avg(cast(followup_completed_7d AS INT)) AS followup_7d_rate,
  avg(risk_score) AS mean_predicted_risk
FROM rtr_demo_catalog.readmission_worklist_gold.readmission_outcome
WHERE was_on_worklist AND readmitted_30d IS NOT NULL
GROUP BY ALL
ORDER BY risk_tier, outreach_group
-- ### program_monthly.obo.sql
SELECT
  date_format(discharge_month, 'yyyy-MM') AS month,
  discharge_month >= date_trunc('MONTH', DATE'2026-05-01') AS in_program,
  MEASURE(discharges) AS discharges,
  MEASURE(readmission_rate) AS readmit_rate,
  MEASURE(followup_7d_rate) AS followup_7d_rate
FROM rtr_demo_catalog.readmission_worklist_gold.readmission_program_metrics
WHERE month_fully_matured
GROUP BY discharge_month
ORDER BY discharge_month
-- ### Outreach coverage of recent worklist days (11-13 left unworked for the live demo, except the check 3 call)
SELECT w.worklist_date, count(*) assigned, count(o.worklist_item_id) with_outreach
FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist w
LEFT JOIN (SELECT DISTINCT worklist_item_id FROM rtr_demo_catalog.care_management_silver.outreach_activity) o USING (worklist_item_id)
WHERE w.worklist_date >= DATE'2026-11-04' AND w.assignment_status = 'ASSIGNED' GROUP BY 1 ORDER BY 1
-- ### Silver outreach equals current CDF state
SELECT (SELECT count(*) FROM rtr_demo_catalog.care_management_silver.outreach_activity) silver_rows,
       (SELECT count(*) FROM (SELECT *, row_number() OVER (PARTITION BY activity_id ORDER BY _pg_lsn DESC, _sort_by DESC) rn
                              FROM rtr_demo_catalog.readmission_worklist_app_bronze.lb_outreach_activity_history) WHERE rn = 1 AND _pg_change_type != 'delete') bronze_current
-- ### Targeting: share of matured program discharges on the worklist vs share of their readmissions (outreach already prevented some readmissions on the worklist, so this understates the model's concentration)
SELECT count(*) matured_program_discharges, round(avg(CAST(was_on_worklist AS INT)) * 100, 1) pct_discharges_on_worklist,
       round(sum(CAST(was_on_worklist AND outcome_status = 'READMITTED' AS INT)) / sum(CAST(outcome_status = 'READMITTED' AS INT)) * 100, 1) pct_readmissions_on_worklist,
       round(avg(CASE WHEN was_on_worklist THEN CAST(outcome_status = 'READMITTED' AS INT) END) * 100, 1) readmit_rate_on_worklist,
       round(avg(CASE WHEN NOT was_on_worklist THEN CAST(outcome_status = 'READMITTED' AS INT) END) * 100, 1) readmit_rate_off_worklist,
       round(count(*) / datediff(max(discharge_date), min(discharge_date)), 1) discharges_per_day
FROM rtr_demo_catalog.readmission_worklist_gold.readmission_outcome
WHERE discharge_date >= DATE'2026-04-30' AND outcome_status <> 'PENDING'
