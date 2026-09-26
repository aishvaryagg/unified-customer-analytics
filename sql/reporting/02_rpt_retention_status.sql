-- Who is still active, side by side. One row per source x population x status.
--   GA4 shoppers:   Active / Churned (no activity in the last CHURN_DAYS days)
--   GA4 customers:  Buying recently / Lapsed (no order in the last CHURN_DAYS days)
--   MIND readers:   Engaged / Passive / Disengaged / Insufficient history
WITH statuses AS (
  SELECT 'GA4' AS source, 'Shoppers' AS population,
    IF(is_churned, 'Churned', 'Active') AS status
  FROM {{ ref('mart_user_rfm_churn') }}
  UNION ALL
  SELECT 'GA4', 'Customers', IF(is_lapsed_purchaser, 'Lapsed', 'Buying recently')
  FROM {{ ref('mart_user_rfm_churn') }}
  WHERE transactions > 0
  UNION ALL
  SELECT 'MIND', 'Readers', engagement_status
  FROM {{ ref('mart_mind__user_disengagement') }}
),

counted AS (
  SELECT source, population, status, COUNT(*) AS people
  FROM statuses
  GROUP BY source, population, status
)

SELECT
  *,
  SAFE_DIVIDE(people, SUM(people) OVER (PARTITION BY source, population)) AS share
FROM counted
