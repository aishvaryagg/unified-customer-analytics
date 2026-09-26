-- Weekly retention by acquisition cohort. A user's cohort is the week of their first
-- session; they count as retained in week N if they had any session N weeks later.
WITH user_weeks AS (
  SELECT DISTINCT user_pseudo_id, session_week
  FROM {{ ref('int_ga4__sessions') }}
),

cohorts AS (
  SELECT user_pseudo_id, MIN(session_week) AS cohort_week
  FROM user_weeks
  GROUP BY user_pseudo_id
),

cohort_sizes AS (
  SELECT cohort_week, COUNT(*) AS cohort_users
  FROM cohorts
  GROUP BY cohort_week
),

activity AS (
  SELECT
    c.cohort_week,
    DIV(DATE_DIFF(w.session_week, c.cohort_week, DAY), 7) AS week_number,
    COUNT(DISTINCT w.user_pseudo_id) AS active_users
  FROM user_weeks AS w
  JOIN cohorts AS c USING (user_pseudo_id)
  GROUP BY c.cohort_week, week_number
)

SELECT
  a.cohort_week,
  a.week_number,
  s.cohort_users,
  a.active_users,
  SAFE_DIVIDE(a.active_users, s.cohort_users) AS retention_rate
FROM activity AS a
JOIN cohort_sizes AS s USING (cohort_week)
