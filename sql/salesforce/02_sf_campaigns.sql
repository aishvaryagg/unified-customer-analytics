-- Salesforce Campaigns: one per GA4 channel + campaign. Performance fields are computed
-- from ALL GA4 sessions, not just the sampled people, so campaign totals are complete.
SELECT
  CONCAT(channel_group, '|', campaign) AS GA4_Campaign_Key__c,
  SUBSTR(CONCAT(channel_group, ' - ', campaign), 1, 80) AS Name,
  CASE channel_group
    WHEN 'Email' THEN 'Email'
    WHEN 'Paid Search' THEN 'Advertisement'
    WHEN 'Display' THEN 'Banner Ads'
    WHEN 'Referral' THEN 'Referral Program'
    WHEN 'Affiliates' THEN 'Partners'
    ELSE 'Other'
  END AS Type,
  'Completed' AS Status,
  FALSE AS IsActive,
  MIN(session_date) AS StartDate,
  MAX(session_date) AS EndDate,
  channel_group AS Channel_Group__c,
  campaign AS GA4_Campaign_Name__c,
  COUNT(*) AS GA4_Sessions__c,
  COUNT(DISTINCT user_pseudo_id) AS GA4_Users__c,
  SUM(transactions) AS GA4_Transactions__c,
  ROUND(SUM(revenue_usd), 2) AS GA4_Revenue__c,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(reached_purchase), COUNT(*)), 2) AS GA4_Conversion_Rate__c
FROM {{ ref('int_ga4__sessions') }}
GROUP BY channel_group, campaign
