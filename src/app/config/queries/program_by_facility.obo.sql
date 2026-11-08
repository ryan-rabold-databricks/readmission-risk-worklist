-- Facility comparison: program period vs the same span one year earlier.
-- @param catalog STRING = rtr_demo_catalog
-- @param go_live DATE = 2026-05-01
WITH o AS (
  SELECT * FROM IDENTIFIER(:catalog || '.readmission_worklist_gold.readmission_outcome')
),
b AS (
  SELECT date_sub(:go_live, 1) AS program_start,
         max(CASE WHEN readmitted_30d IS NOT NULL THEN discharge_date END) AS matured_through
  FROM o
),
tagged AS (
  SELECT o.*, b.matured_through,
    CASE WHEN o.discharge_date >= b.program_start THEN 'program'
         WHEN o.discharge_date >= add_months(b.program_start, -12)
          AND o.discharge_date <= add_months(b.matured_through, -12) THEN 'baseline' END AS period
  FROM o, b
)
SELECT
  t.facility_id,
  f.facility_name,
  sum(CASE WHEN period = 'program' THEN 1 ELSE 0 END) AS program_discharges,
  avg(CASE WHEN period = 'program' THEN cast(readmitted_30d AS INT) END) AS program_readmit_rate,
  avg(CASE WHEN period = 'baseline' THEN cast(readmitted_30d AS INT) END) AS baseline_readmit_rate,
  -- Through matured_through, the same span as the readmission rate and the baseline.
  avg(CASE WHEN period = 'program' AND t.discharge_date <= t.matured_through THEN cast(followup_completed_7d AS INT) END) AS program_followup_7d_rate,
  avg(CASE WHEN period = 'program' AND assignment_status = 'ASSIGNED' THEN cast(was_reached AS INT) END) AS reach_rate,
  sum(CASE WHEN period = 'program' AND assignment_status = 'OVERFLOW' THEN 1 ELSE 0 END) AS overflow_items
FROM tagged t
JOIN IDENTIFIER(:catalog || '.clinical_silver.facility') f USING (facility_id)
WHERE period IS NOT NULL
GROUP BY ALL
ORDER BY program_readmit_rate DESC
