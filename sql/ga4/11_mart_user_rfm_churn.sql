-- One row per user: activity, recency/frequency/monetary (RFM) scores, and churn flags.
--
-- The reference date is GA4_END_DATE, the last day of the data.
--   is_churned            no activity of any kind in the last CHURN_DAYS days
--   is_lapsed_purchaser   has purchased, but not in the last CHURN_DAYS days
-- RFM scores run 1-5 (5 = best) and are computed among purchasers only.
WITH user_activity AS (
  SELECT
    user_pseudo_id,
    MIN(event_date) AS first_seen_date,
    MAX(event_date) AS last_seen_date,
    COUNT(DISTINCT session_key) AS sessions
  FROM {{ ref('stg_ga4__events') }}
  GROUP BY user_pseudo_id
),

user_purchases AS (
  SELECT
    user_pseudo_id,
    MAX(purchase_date) AS last_purchase_date,
    COUNT(*) AS transactions,
    SUM(COALESCE(revenue_usd, 0)) AS revenue_usd
  FROM {{ ref('stg_ga4__purchases') }}
  GROUP BY user_pseudo_id
),

joined AS (
  SELECT
    a.user_pseudo_id,
    a.first_seen_date,
    a.last_seen_date,
    a.sessions,
    p.last_purchase_date,
    COALESCE(p.transactions, 0) AS transactions,
    COALESCE(p.revenue_usd, 0) AS revenue_usd,
    DATE_DIFF(DATE '{{ params.ga4_end_date_iso }}', a.last_seen_date, DAY) AS days_since_last_seen,
    DATE_DIFF(DATE '{{ params.ga4_end_date_iso }}', p.last_purchase_date, DAY) AS days_since_last_purchase
  FROM user_activity AS a
  LEFT JOIN user_purchases AS p USING (user_pseudo_id)
),

scored AS (
  SELECT
    *,
    IF(transactions > 0,
      NTILE(5) OVER (
        PARTITION BY transactions > 0 ORDER BY days_since_last_purchase DESC, user_pseudo_id
      ), NULL) AS recency_score,
    IF(transactions > 0,
      NTILE(5) OVER (PARTITION BY transactions > 0 ORDER BY transactions, user_pseudo_id), NULL
    ) AS frequency_score,
    IF(transactions > 0,
      NTILE(5) OVER (PARTITION BY transactions > 0 ORDER BY revenue_usd, user_pseudo_id), NULL
    ) AS monetary_score
  FROM joined
)

SELECT
  *,
  days_since_last_seen > {{ params.churn_days }} AS is_churned,
  transactions > 0 AND days_since_last_purchase > {{ params.churn_days }} AS is_lapsed_purchaser,
  CASE
    WHEN transactions = 0 THEN 'Non-purchaser'
    WHEN recency_score >= 4 AND frequency_score >= 4 THEN 'Champion'
    WHEN recency_score >= 4 THEN 'Recent customer'
    WHEN frequency_score >= 4 OR monetary_score >= 4 THEN 'At-risk high value'
    ELSE 'Lapsing customer'
  END AS rfm_segment
FROM scored
