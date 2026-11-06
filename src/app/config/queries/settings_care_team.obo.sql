-- Care team in effect on :as_of: facilities and daily capacity per care manager.
-- @param catalog STRING = rtr_demo_catalog
-- @param as_of DATE = 2026-11-07
WITH a AS (
  SELECT care_manager_email, sort_array(collect_list(facility_id)) AS facility_ids
  FROM IDENTIFIER(:catalog || '.care_management_silver.care_team_assignment')
  WHERE effective_date <= :as_of AND (expiration_date IS NULL OR expiration_date > :as_of)
  GROUP BY care_manager_email
),
c AS (
  SELECT care_manager_email, daily_capacity
  FROM IDENTIFIER(:catalog || '.care_management_silver.care_manager_capacity')
  WHERE effective_date <= :as_of AND (expiration_date IS NULL OR expiration_date > :as_of)
)
SELECT coalesce(a.care_manager_email, c.care_manager_email) AS care_manager_email,
       coalesce(a.facility_ids, array()) AS facility_ids,
       c.daily_capacity
FROM a FULL OUTER JOIN c ON a.care_manager_email = c.care_manager_email
ORDER BY care_manager_email
