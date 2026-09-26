-- Salesforce Account. GA4 shoppers are individual consumers, so they all sit under one
-- house account (a common pattern for B2C data in an org without Person Accounts).
SELECT
  'ga4-online-store' AS GA4_Account_Key__c,
  'Google Merchandise Store - Online Customers' AS Name,
  'Customer' AS Type,
  'Retail' AS Industry
