-- Salesforce Opportunities: every order placed by a sampled contact, as Closed Won.
-- Primary Campaign Source (CampaignId) is the last-touch campaign: the campaign of the
-- session the order was placed in. First- and last-touch channels are stored as well.
SELECT
  p.transaction_key AS GA4_Transaction_Id__c,
  'ga4-online-store' AS account_key,
  p.user_pseudo_id AS contact_key,
  CONCAT(s.channel_group, '|', s.campaign) AS campaign_key,
  SUBSTR(CONCAT('GA4 order ', p.transaction_key), 1, 120) AS Name,
  'Closed Won' AS StageName,
  p.purchase_date AS CloseDate,
  ROUND(COALESCE(p.revenue_usd, 0), 2) AS Amount,
  c.acquisition_channel AS First_Touch_Channel__c,
  s.channel_group AS Last_Touch_Channel__c,
  p.total_item_quantity AS GA4_Item_Quantity__c
FROM {{ ref('stg_ga4__purchases') }} AS p
JOIN {{ ref('int_sf__people') }} AS c
  ON c.user_pseudo_id = p.user_pseudo_id
 AND c.crm_type = 'Contact'
 AND c.in_sample
LEFT JOIN {{ ref('int_ga4__sessions') }} AS s USING (session_key)
