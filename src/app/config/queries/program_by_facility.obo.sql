-- Facility comparison, program period vs the same span one year earlier, from the governed
-- metric view (DECISIONS.md #61). Reach rate excludes the latest worklist day, as in the
-- headline KPI.
-- @param catalog STRING = rtr_demo_catalog
SELECT
  facility_id,
  facility_name,
  MEASURE(program_discharges) AS program_discharges,
  MEASURE(program_readmission_rate) AS program_readmit_rate,
  MEASURE(baseline_readmission_rate) AS baseline_readmit_rate,
  MEASURE(program_followup_7d_rate) AS program_followup_7d_rate,
  MEASURE(reach_rate) AS reach_rate,
  MEASURE(overflow_items) AS overflow_items
FROM IDENTIFIER(:catalog || '.readmission_worklist_gold.readmission_program_metrics')
WHERE period IS NOT NULL
GROUP BY facility_id, facility_name
ORDER BY program_readmit_rate DESC
