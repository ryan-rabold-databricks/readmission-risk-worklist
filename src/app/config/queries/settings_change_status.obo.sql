-- Pipeline validation result for each Program Settings change (latest first).
-- @param catalog STRING = rtr_demo_catalog
SELECT change_id, setting_type, target_key, effective_date, changed_by, changed_at, status, status_reason
FROM IDENTIFIER(:catalog || '.care_management_silver.program_setting')
ORDER BY changed_at DESC
LIMIT 100
