-- Salesforce Campaign Members: which campaigns each sampled contact or lead arrived through.
-- Status is 'Responded' if they added to cart or bought in a session from that campaign,
-- otherwise 'Sent' (both are default Campaign Member statuses).
SELECT
  CONCAT(s.channel_group, '|', s.campaign) AS campaign_key,
  IF(p.crm_type = 'Contact', s.user_pseudo_id, NULL) AS contact_key,
  IF(p.crm_type = 'Lead', s.user_pseudo_id, NULL) AS lead_key,
  IF(LOGICAL_OR(s.reached_add_to_cart OR s.reached_purchase), 'Responded', 'Sent') AS Status
FROM {{ ref('int_ga4__sessions') }} AS s
JOIN {{ ref('int_sf__people') }} AS p
  ON p.user_pseudo_id = s.user_pseudo_id
 AND p.in_sample
GROUP BY s.channel_group, s.campaign, s.user_pseudo_id, p.crm_type
