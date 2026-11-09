-- Program headline KPIs from the governed metric view
-- readmission_worklist_gold.readmission_program_metrics, the one definition shared with
-- the Genie Agent (DECISIONS.md #57-#59, #61). Period bounds, both cost-avoided methods
-- (within tier, headline; vs prior year, cross-check), and the assumed cost per
-- readmission are defined in the view (src/readmit/governance/readmission_program_metrics.yaml).
-- @param catalog STRING = rtr_demo_catalog
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
FROM IDENTIFIER(:catalog || '.readmission_worklist_gold.readmission_program_metrics')
