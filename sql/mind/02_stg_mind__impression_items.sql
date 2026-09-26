-- One row per article shown in an impression, and whether the reader clicked it.
-- The raw field looks like "N123-1 N456-0": news id, then 1 = clicked, 0 = not clicked.
SELECT
  i.impression_key,
  i.user_id,
  i.impression_ts,
  i.impression_date,
  SPLIT(shown, '-')[OFFSET(0)] AS news_id,
  SPLIT(shown, '-')[SAFE_OFFSET(1)] = '1' AS clicked
FROM {{ ref('stg_mind__impressions') }} AS i
CROSS JOIN UNNEST(SPLIT(i.impressions, ' ')) AS shown
WHERE shown != ''
