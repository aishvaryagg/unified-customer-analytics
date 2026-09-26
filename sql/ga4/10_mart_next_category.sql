-- Cross-category cross-sell: after buying from category A, which *new* category does a
-- customer buy from in their next purchase?
--
-- For each pair of a user's consecutive purchases, every category in the earlier purchase
-- is linked to every category in the later purchase that the earlier one did not contain.
--   probability  of consecutive-purchase pairs whose first purchase included from_category,
--                the share whose next purchase added to_category
-- Segments: all customers, and each first-touch acquisition channel.
-- Items with a missing or obfuscated category are excluded.
WITH transactions AS (
  SELECT
    transaction_key,
    user_pseudo_id,
    ROW_NUMBER() OVER (
      PARTITION BY user_pseudo_id ORDER BY purchase_ts, transaction_key
    ) AS purchase_number
  FROM {{ ref('stg_ga4__purchases') }}
),

categories AS (
  SELECT DISTINCT transaction_key, item_category AS category
  FROM {{ ref('stg_ga4__items') }}
  WHERE event_name = 'purchase' AND {{ is_known('item_category') }}
),

segments AS (
  SELECT
    user_pseudo_id,
    {{ channel_group('first_touch_source', 'first_touch_medium') }} AS acquisition_channel
  FROM {{ ref('stg_ga4__events') }}
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_pseudo_id ORDER BY event_ts, event_id) = 1
),

consecutive AS (
  SELECT
    a.user_pseudo_id,
    a.transaction_key AS from_transaction,
    b.transaction_key AS to_transaction
  FROM transactions AS a
  JOIN transactions AS b
    ON a.user_pseudo_id = b.user_pseudo_id
   AND b.purchase_number = a.purchase_number + 1
),

from_side AS (
  SELECT c.user_pseudo_id, c.from_transaction, c.to_transaction, fc.category AS from_category
  FROM consecutive AS c
  JOIN categories AS fc ON fc.transaction_key = c.from_transaction
),

transitions AS (
  SELECT f.user_pseudo_id, f.from_transaction, f.from_category, tc.category AS to_category
  FROM from_side AS f
  JOIN categories AS tc ON tc.transaction_key = f.to_transaction
  LEFT JOIN categories AS already
    ON already.transaction_key = f.from_transaction
   AND already.category = tc.category
  WHERE already.transaction_key IS NULL
),

segmented_from AS (
  SELECT 'All customers' AS segment, from_transaction, from_category FROM from_side
  UNION ALL
  SELECT s.acquisition_channel, f.from_transaction, f.from_category
  FROM from_side AS f JOIN segments AS s USING (user_pseudo_id)
),

segmented_transitions AS (
  SELECT 'All customers' AS segment, from_category, to_category FROM transitions
  UNION ALL
  SELECT s.acquisition_channel, t.from_category, t.to_category
  FROM transitions AS t JOIN segments AS s USING (user_pseudo_id)
),

base AS (
  SELECT segment, from_category, COUNT(*) AS purchase_pairs
  FROM segmented_from
  GROUP BY segment, from_category
),

counted AS (
  SELECT segment, from_category, to_category, COUNT(*) AS transitions
  FROM segmented_transitions
  GROUP BY segment, from_category, to_category
)

SELECT
  c.segment,
  c.from_category,
  c.to_category,
  c.transitions,
  b.purchase_pairs,
  SAFE_DIVIDE(c.transitions, b.purchase_pairs) AS probability,
  ROW_NUMBER() OVER (
    PARTITION BY c.segment, c.from_category ORDER BY c.transitions DESC, c.to_category
  ) AS rank_in_segment
FROM counted AS c
JOIN base AS b USING (segment, from_category)
