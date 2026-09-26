-- One row per GA4 user with everything the CRM needs, and whether they are in the sample
-- sent to Salesforce.
--   Contact  a purchaser
--   Lead     a non-purchaser who added to cart or started checkout (showed buying intent)
-- A Developer Edition org holds only ~2,500 records, so at most SF_MAX_CONTACTS contacts
-- and SF_MAX_LEADS leads are sent. They are picked by an MD5 hash of the user id: a
-- repeatable pseudo-random sample, so rebuilding sends the same people.
--
-- These records are pseudonymous: GA4 has no names or emails, and none are invented.
WITH acquisition AS (
  SELECT
    user_pseudo_id,
    {{ channel_group('first_touch_source', 'first_touch_medium') }} AS acquisition_channel
  FROM {{ ref('stg_ga4__events') }}
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY event_ts, event_id) = 1
),

intent AS (
  SELECT
    user_pseudo_id,
    LOGICAL_OR(reached_add_to_cart) AS reached_add_to_cart,
    LOGICAL_OR(reached_checkout) AS reached_checkout
  FROM {{ ref('int_ga4__sessions') }}
  GROUP BY user_pseudo_id
),

people AS (
  SELECT
    r.*,
    a.acquisition_channel,
    t.latest_trend AS revenue_trend,
    CASE
      WHEN r.transactions > 0 THEN 'Contact'
      WHEN i.reached_checkout OR i.reached_add_to_cart THEN 'Lead'
    END AS crm_type,
    CASE
      WHEN i.reached_checkout THEN 'Checkout'
      WHEN i.reached_add_to_cart THEN 'Add to cart'
    END AS highest_funnel_stage,
    TO_HEX(MD5(r.user_pseudo_id)) AS sample_hash
  FROM {{ ref('mart_user_rfm_churn') }} AS r
  LEFT JOIN acquisition AS a USING (user_pseudo_id)
  LEFT JOIN intent AS i USING (user_pseudo_id)
  LEFT JOIN {{ ref('mart_user_revenue_trend') }} AS t USING (user_pseudo_id)
),

ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY crm_type ORDER BY sample_hash) AS sample_rank
  FROM people
  WHERE crm_type IS NOT NULL
)

SELECT
  *,
  (crm_type = 'Contact' AND sample_rank <= {{ params.sf_max_contacts }})
    OR (crm_type = 'Lead' AND sample_rank <= {{ params.sf_max_leads }}) AS in_sample
FROM ranked
