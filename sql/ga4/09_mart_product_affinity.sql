-- Which products are bought together. One row per ordered pair (A -> B) of products that
-- appear in the same transaction.
--   support     share of all transactions containing both
--   confidence  of transactions containing A, the share that also contain B
--   lift        confidence / share of transactions containing B (> 1 means bought
--               together more often than chance)
-- Products whose name is missing or obfuscated are excluded.
WITH basket AS (
  SELECT DISTINCT transaction_key, item_name AS product
  FROM {{ ref('stg_ga4__items') }}
  WHERE event_name = 'purchase' AND {{ is_known('item_name') }}
),

totals AS (
  SELECT COUNT(DISTINCT transaction_key) AS transactions FROM basket
),

product_counts AS (
  SELECT product, COUNT(*) AS transactions_with_product
  FROM basket
  GROUP BY product
),

pairs AS (
  SELECT a.product AS product_a, b.product AS product_b, COUNT(*) AS transactions_with_both
  FROM basket AS a
  JOIN basket AS b
    ON a.transaction_key = b.transaction_key
   AND a.product != b.product
  GROUP BY a.product, b.product
)

SELECT
  p.product_a,
  p.product_b,
  p.transactions_with_both,
  ca.transactions_with_product AS transactions_with_a,
  cb.transactions_with_product AS transactions_with_b,
  SAFE_DIVIDE(p.transactions_with_both, t.transactions) AS support,
  SAFE_DIVIDE(p.transactions_with_both, ca.transactions_with_product) AS confidence,
  SAFE_DIVIDE(
    SAFE_DIVIDE(p.transactions_with_both, ca.transactions_with_product),
    SAFE_DIVIDE(cb.transactions_with_product, t.transactions)
  ) AS lift
FROM pairs AS p
CROSS JOIN totals AS t
JOIN product_counts AS ca ON ca.product = p.product_a
JOIN product_counts AS cb ON cb.product = p.product_b
