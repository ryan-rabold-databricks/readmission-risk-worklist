-- Risk tier policy versions in effect today or scheduled (applied by the pipeline).
-- @param catalog STRING = rtr_demo_catalog
SELECT risk_tier, min_score, max_score, outreach_sla_hours, include_in_worklist,
       effective_date, expiration_date, audit_created_by AS set_by, audit_created_run_id AS source
FROM IDENTIFIER(:catalog || '.care_management_silver.risk_tier_policy')
WHERE is_active AND (expiration_date IS NULL OR expiration_date > current_date())
ORDER BY effective_date, min_score DESC
