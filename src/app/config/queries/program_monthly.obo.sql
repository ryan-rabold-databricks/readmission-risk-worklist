-- Monthly trend by discharge month (YYYY-MM) from the governed metric view
-- (DECISIONS.md #61). Only months whose every 30-day readmission window has closed
-- (month_fully_matured), so the latest months never show a falsely low rate.
-- @param catalog STRING = rtr_demo_catalog
-- @param go_live DATE = 2026-05-01
SELECT
  date_format(discharge_month, 'yyyy-MM') AS month,
  discharge_month >= date_trunc('MONTH', :go_live) AS in_program,
  MEASURE(discharges) AS discharges,
  MEASURE(readmission_rate) AS readmit_rate,
  MEASURE(followup_7d_rate) AS followup_7d_rate
FROM IDENTIFIER(:catalog || '.readmission_worklist_gold.readmission_program_metrics')
WHERE month_fully_matured
GROUP BY discharge_month
ORDER BY discharge_month
