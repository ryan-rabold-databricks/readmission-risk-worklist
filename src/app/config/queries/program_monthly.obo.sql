-- Monthly trend by discharge month (YYYY-MM): readmission rate and 7-day follow-up rate.
-- Only months whose every 30-day readmission window has closed in the data, so the
-- latest months never show a falsely low rate.
-- @param catalog STRING = rtr_demo_catalog
-- @param go_live DATE = 2026-05-01
WITH o AS (
  SELECT * FROM IDENTIFIER(:catalog || '.readmission_worklist_gold.readmission_outcome')
),
m AS (
  SELECT
    date_trunc('MONTH', discharge_date) AS month_start,
    count(*) AS discharges,
    count(readmitted_30d) AS matured_discharges,
    avg(cast(readmitted_30d AS INT)) AS readmit_rate,
    avg(cast(followup_completed_7d AS INT)) AS followup_7d_rate
  FROM o
  GROUP BY ALL
)
SELECT
  date_format(month_start, 'yyyy-MM') AS month,
  month_start >= date_trunc('MONTH', :go_live) AS in_program,
  discharges,
  readmit_rate,
  followup_7d_rate
FROM m
WHERE matured_discharges = discharges
ORDER BY month
