-- Salesforce Contacts: sampled purchasers, with their GA4 marketing profile.
-- Next best category: from the customer's most recent purchase, the category most likely
-- to be bought next (mart_next_category), for their acquisition channel if that segment
-- has data, otherwise across all customers. Categories already in that purchase are skipped.
WITH contacts AS (
  SELECT * FROM {{ ref('int_sf__people') }}
  WHERE crm_type = 'Contact' AND in_sample
),

last_purchase AS (
  SELECT user_pseudo_id, transaction_key
  FROM {{ ref('stg_ga4__purchases') }}
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY user_pseudo_id ORDER BY purchase_ts DESC, transaction_key DESC
  ) = 1
),

last_categories AS (
  SELECT DISTINCT l.user_pseudo_id, i.item_category AS category
  FROM last_purchase AS l
  JOIN {{ ref('stg_ga4__items') }} AS i
    ON i.transaction_key = l.transaction_key
   AND i.event_name = 'purchase'
  WHERE {{ is_known('i.item_category') }}
),

candidates AS (
  SELECT lc.user_pseudo_id, n.to_category, n.probability, 0 AS preference
  FROM last_categories AS lc
  JOIN contacts AS c USING (user_pseudo_id)
  JOIN {{ ref('mart_next_category') }} AS n
    ON n.segment = c.acquisition_channel
   AND n.from_category = lc.category
  UNION ALL
  SELECT lc.user_pseudo_id, n.to_category, n.probability, 1
  FROM last_categories AS lc
  JOIN {{ ref('mart_next_category') }} AS n
    ON n.segment = 'All customers'
   AND n.from_category = lc.category
),

next_best AS (
  SELECT c.user_pseudo_id, c.to_category, c.probability
  FROM candidates AS c
  LEFT JOIN last_categories AS owned
    ON owned.user_pseudo_id = c.user_pseudo_id
   AND owned.category = c.to_category
  WHERE owned.user_pseudo_id IS NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY c.user_pseudo_id ORDER BY c.preference, c.probability DESC, c.to_category
  ) = 1
)

SELECT
  c.user_pseudo_id AS GA4_User_Pseudo_Id__c,
  'ga4-online-store' AS account_key,
  CONCAT('GA4 Customer ', SUBSTR(c.sample_hash, 1, 8)) AS LastName,
  'Web' AS LeadSource,
  c.acquisition_channel AS Acquisition_Channel__c,
  c.first_seen_date AS First_Seen_Date__c,
  c.last_seen_date AS Last_Seen_Date__c,
  c.last_purchase_date AS Last_Purchase_Date__c,
  c.sessions AS GA4_Sessions__c,
  c.transactions AS GA4_Transactions__c,
  ROUND(c.revenue_usd, 2) AS Lifetime_Revenue__c,
  c.recency_score AS Recency_Score__c,
  c.frequency_score AS Frequency_Score__c,
  c.monetary_score AS Monetary_Score__c,
  c.rfm_segment AS RFM_Segment__c,
  c.revenue_trend AS Revenue_Trend__c,
  c.is_churned AS Is_Churned__c,
  c.is_lapsed_purchaser AS Is_Lapsed_Purchaser__c,
  nb.to_category AS Next_Best_Category__c,
  ROUND(100 * nb.probability, 2) AS Next_Best_Category_Probability__c
FROM contacts AS c
LEFT JOIN next_best AS nb USING (user_pseudo_id)
