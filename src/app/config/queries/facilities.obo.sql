-- Active facilities, for names and the care team form.
-- @param catalog STRING = rtr_demo_catalog
SELECT facility_id, facility_name, region
FROM IDENTIFIER(:catalog || '.clinical_silver.facility')
WHERE is_active
ORDER BY facility_name
