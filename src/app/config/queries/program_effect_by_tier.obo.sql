-- Readmission rate of worked worklist items by tier and outreach result (matured labels),
-- next to the model's mean predicted risk so groups are compared at similar risk.
-- @param catalog STRING = rtr_demo_catalog
SELECT
  risk_tier,
  CASE WHEN assignment_status = 'OVERFLOW' THEN 'Overflow (not worked)'
       WHEN was_reached THEN 'Reached'
       ELSE 'Assigned, not reached' END AS outreach_group,
  count(*) AS items,
  avg(cast(readmitted_30d AS INT)) AS readmit_rate,
  avg(cast(followup_completed_7d AS INT)) AS followup_7d_rate,
  avg(risk_score) AS mean_predicted_risk
FROM IDENTIFIER(:catalog || '.readmission_worklist_gold.readmission_outcome')
WHERE was_on_worklist AND readmitted_30d IS NOT NULL
GROUP BY ALL
ORDER BY risk_tier, outreach_group
