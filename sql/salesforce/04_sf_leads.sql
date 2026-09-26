-- Salesforce Leads: sampled non-purchasers who added to cart or started checkout.
-- Company is required on Leads; 'Individual' is the usual B2C placeholder.
SELECT
  user_pseudo_id AS GA4_User_Pseudo_Id__c,
  CONCAT('GA4 Visitor ', SUBSTR(sample_hash, 1, 8)) AS LastName,
  'Individual' AS Company,
  'Web' AS LeadSource,
  'Open - Not Contacted' AS Status,
  acquisition_channel AS Acquisition_Channel__c,
  highest_funnel_stage AS Highest_Funnel_Stage__c,
  first_seen_date AS First_Seen_Date__c,
  last_seen_date AS Last_Seen_Date__c,
  sessions AS GA4_Sessions__c,
  is_churned AS Is_Churned__c
FROM {{ ref('int_sf__people') }}
WHERE crm_type = 'Lead' AND in_sample
