-- Program headline KPIs. Program period: discharges from go-live - 1 day (worklist day W
-- covers discharges on W - 1). Baseline: the same calendar span one year earlier.
-- Readmission rates use matured labels only; reach rate uses ASSIGNED worklist items
-- released before the latest worklist day (today's items are still being worked).
-- Estimated readmissions avoided: per risk tier, (not-reached rate - reached rate) x reached
-- items, over matured ASSIGNED items; a within-tier comparison, not a causal estimate.
-- @param catalog STRING = rtr_demo_catalog
-- @param go_live DATE = 2026-05-01
-- @param avg_cost DOUBLE
WITH o AS (
  SELECT * FROM IDENTIFIER(:catalog || '.readmission_worklist_gold.readmission_outcome')
),
bounds AS (
  SELECT
    date_sub(:go_live, 1) AS program_start,
    max(CASE WHEN readmitted_30d IS NOT NULL THEN discharge_date END) AS matured_through,
    max(discharge_date) AS data_through,
    max(worklist_date) AS latest_worklist_date
  FROM o
),
program AS (
  SELECT o.* FROM o, bounds b WHERE o.discharge_date >= b.program_start
),
baseline AS (
  SELECT o.* FROM o, bounds b
  WHERE o.discharge_date >= add_months(b.program_start, -12)
    AND o.discharge_date <= add_months(b.matured_through, -12)
),
tier_effect AS (
  SELECT risk_tier,
    sum(CASE WHEN was_reached THEN 1 ELSE 0 END) AS reached_n,
    avg(CASE WHEN was_reached THEN cast(readmitted_30d AS INT) END) AS reached_rate,
    avg(CASE WHEN NOT was_reached THEN cast(readmitted_30d AS INT) END) AS not_reached_rate
  FROM program
  WHERE assignment_status = 'ASSIGNED' AND readmitted_30d IS NOT NULL
  GROUP BY risk_tier
),
avoided AS (
  SELECT coalesce(sum(greatest(not_reached_rate - reached_rate, 0) * reached_n), 0) AS readmissions_avoided
  FROM tier_effect
)
SELECT
  b.program_start,
  b.matured_through,
  b.data_through,
  b.latest_worklist_date,
  (SELECT count(*) FROM program) AS program_discharges,
  (SELECT avg(cast(readmitted_30d AS INT)) FROM program WHERE readmitted_30d IS NOT NULL) AS program_readmit_rate,
  (SELECT avg(cast(readmitted_30d AS INT)) FROM baseline WHERE readmitted_30d IS NOT NULL) AS baseline_readmit_rate,
  (SELECT avg(cast(followup_completed_7d AS INT)) FROM program) AS program_followup_7d_rate,
  (SELECT avg(cast(followup_completed_7d AS INT)) FROM baseline) AS baseline_followup_7d_rate,
  (SELECT avg(cast(was_reached AS INT)) FROM program
     WHERE assignment_status = 'ASSIGNED' AND worklist_date < b.latest_worklist_date) AS reach_rate,
  (SELECT count(*) FROM program WHERE was_on_worklist) AS worklist_items,
  (SELECT count(*) FROM program WHERE assignment_status = 'OVERFLOW') AS overflow_items,
  (SELECT percentile_approx(first_contact_hours, 0.5) FROM program WHERE was_reached) AS median_first_contact_hours,
  a.readmissions_avoided,
  a.readmissions_avoided * :avg_cost AS est_cost_avoided
FROM bounds b CROSS JOIN avoided a
