-- Headline numbers for dashboards and the Sheets summary: one row per metric.
-- GA4 and MIND metrics sit in the same table but describe different businesses and
-- different people; they are never combined into one number.
--   unit: 'count', 'usd' or 'ratio' (0-1; format as a percentage)
WITH ga4_sessions AS (
  SELECT
    COUNT(*) AS sessions,
    COUNT(DISTINCT user_pseudo_id) AS users,
    COUNTIF(reached_purchase) AS converting_sessions,
    SUM(transactions) AS transactions,
    SUM(revenue_usd) AS revenue_usd
  FROM {{ ref('int_ga4__sessions') }}
),

ga4_users AS (
  SELECT
    COUNT(*) AS users,
    COUNTIF(transactions > 0) AS customers,
    COUNTIF(is_churned) AS churned_users,
    COUNTIF(is_lapsed_purchaser) AS lapsed_customers
  FROM {{ ref('mart_user_rfm_churn') }}
),

mind_totals AS (
  SELECT
    COUNT(*) AS readers,
    SUM(impressions) AS impressions,
    SUM(clicks) AS clicks,
    COUNTIF(engagement_status = 'Disengaged') AS disengaged,
    COUNTIF(engagement_status = 'Passive') AS passive
  FROM {{ ref('mart_mind__user_disengagement') }}
),

mind_shown AS (
  SELECT SUM(articles_shown) AS articles_shown
  FROM {{ ref('mart_mind__user_engagement_trend') }}
),

mind_drift AS (
  SELECT COUNT(DISTINCT user_id) AS drifting_readers
  FROM {{ ref('mart_mind__topic_drift') }}
  WHERE direction = 'Drifting away'
),

metrics AS (
  SELECT 'GA4' AS source, 1 AS sort_order, 'sessions' AS metric, 'Sessions' AS label,
    CAST(sessions AS FLOAT64) AS value, 'count' AS unit, 'Visits to the online store.' AS definition
  FROM ga4_sessions
  UNION ALL SELECT 'GA4', 2, 'users', 'Users', CAST(users AS FLOAT64), 'count',
    'Distinct shoppers (GA4 user_pseudo_id).' FROM ga4_sessions
  UNION ALL SELECT 'GA4', 3, 'transactions', 'Orders', CAST(transactions AS FLOAT64), 'count',
    'Orders, duplicates removed.' FROM ga4_sessions
  UNION ALL SELECT 'GA4', 4, 'revenue_usd', 'Revenue', revenue_usd, 'usd',
    'Order revenue in USD.' FROM ga4_sessions
  UNION ALL SELECT 'GA4', 5, 'conversion_rate', 'Conversion rate',
    SAFE_DIVIDE(converting_sessions, sessions), 'ratio',
    'Sessions with a purchase / sessions.' FROM ga4_sessions
  UNION ALL SELECT 'GA4', 6, 'avg_order_value_usd', 'Average order value',
    SAFE_DIVIDE(revenue_usd, transactions), 'usd', 'Revenue / orders.' FROM ga4_sessions
  UNION ALL SELECT 'GA4', 7, 'customers', 'Customers', CAST(customers AS FLOAT64), 'count',
    'Shoppers with at least one order.' FROM ga4_users
  UNION ALL SELECT 'GA4', 8, 'churned_share', 'Churned shoppers',
    SAFE_DIVIDE(churned_users, users), 'ratio',
    'Share of shoppers with no activity in the last CHURN_DAYS days of the data.' FROM ga4_users
  UNION ALL SELECT 'GA4', 9, 'lapsed_customer_share', 'Lapsed customers',
    SAFE_DIVIDE(lapsed_customers, customers), 'ratio',
    'Share of customers with no order in the last CHURN_DAYS days.' FROM ga4_users
  UNION ALL SELECT 'MIND', 11, 'readers', 'Readers', CAST(readers AS FLOAT64), 'count',
    'Distinct news readers in the impression log.' FROM mind_totals
  UNION ALL SELECT 'MIND', 12, 'impressions', 'Impressions', CAST(impressions AS FLOAT64), 'count',
    'Page loads that showed a list of articles.' FROM mind_totals
  UNION ALL SELECT 'MIND', 13, 'clicks', 'Clicks', CAST(clicks AS FLOAT64), 'count',
    'Articles clicked.' FROM mind_totals
  UNION ALL SELECT 'MIND', 14, 'click_through_rate', 'Click-through rate',
    SAFE_DIVIDE(clicks, articles_shown), 'ratio', 'Clicks / articles shown.'
  FROM mind_totals CROSS JOIN mind_shown
  UNION ALL SELECT 'MIND', 15, 'disengaged_share', 'Disengaged readers',
    SAFE_DIVIDE(disengaged, readers), 'ratio',
    'Share of readers with no impressions in the last MIND_DISENGAGED_DAYS days.' FROM mind_totals
  UNION ALL SELECT 'MIND', 16, 'passive_share', 'Passive readers',
    SAFE_DIVIDE(passive, readers), 'ratio',
    'Share of readers still shown articles recently but not clicking.' FROM mind_totals
  UNION ALL SELECT 'MIND', 17, 'drifting_readers', 'Readers drifting from a topic',
    CAST(drifting_readers AS FLOAT64), 'count',
    'Readers whose share of clicks on a category fell by at least MIND_DRIFT_THRESHOLD.'
  FROM mind_drift
)

SELECT * FROM metrics
