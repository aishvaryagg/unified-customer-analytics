# Methodology

How each GA4 metric is defined, and the decisions behind the definitions. MIND methodology
will be added with the MIND models.

## Data limitations

Stated here, where the data is first used, rather than in an appendix.

**GA4 obfuscated sample.** Google publishes this dataset as *obfuscated sample data* from
the Google Merchandise Store's GA4 property, 1 Nov 2020 – 31 Jan 2021. Google describes its
internal consistency as limited. In practice:

- Some values are replaced with `<Other>` or `(data deleted)`. These are labelled
  `(obfuscated)` (or channel `Obfuscated`) instead of being silently dropped or merged
  with real values.
- GA4 writes `(not set)` when a value was never collected.
- Products or categories with placeholder values are excluded from the affinity and
  cross-sell models, since a pair like "`(not set)` → `(not set)`" is meaningless.
- `dq_ga4__placeholder_share` reports, per field, how many rows hold a placeholder. Read it
  before quoting any channel or product figure.
- Results describe this sample, not the real store's performance.

**Revenue** is `ecommerce.purchase_revenue_in_usd` (GA4's USD-converted value), so all
revenue is in one currency.

## Building blocks

**Session.** GA4's `ga_session_id` is only unique per user, so a session is identified by
`user_pseudo_id` + `ga_session_id`. Events without a session id count toward user activity
but not toward session models.

**Transaction.** GA4 can record one purchase more than once. Purchases are deduplicated on
`transaction_id`, keeping the earliest event. A purchase whose `transaction_id` is missing or
a placeholder counts as its own transaction.

**Session source, medium and campaign.** Taken from the first event in the session that
carries `source` / `medium` / `campaign` parameters. A session with none of them is treated
as direct (`(direct)` / `(none)`). GA4's own reports go further and credit such sessions to
the user's last non-direct source; this project does not.

**Channel group.** A simplified version of GA4's default channel grouping:

| Rule (first match wins) | Channel |
|---|---|
| source or medium is `<Other>` / `(data deleted)` | Obfuscated |
| source `(direct)` and medium `(none)` / `(not set)` | Direct |
| medium `organic` | Organic Search |
| medium `cpc`, `ppc`, `paidsearch` | Paid Search |
| medium contains `social`, or a known social source | Social |
| medium `email` | Email |
| medium `affiliate` | Affiliates |
| medium `display`, `cpm`, `banner` | Display |
| medium `referral` | Referral |
| anything else | Unassigned |

**Week.** Weeks start on Monday. Dates are GA4's `event_date`, in the property's reporting
time zone, so daily numbers line up with GA4's own reports.

## Funnel (`mart_funnel_daily`)

Stages: session → `view_item` → `add_to_cart` → `begin_checkout` → `purchase`. A session
reaches a stage if it fired that event at least once. Step rates divide each stage by the
one before it. When the earlier stage is zero the rate is empty (undefined), not 0%.

Sessions can skip stages (for example, a purchase with no recorded `view_item`), so a later
stage can occasionally exceed an earlier one in this sample.

## Channel performance (`mart_channel_performance`)

Session-scoped: each session's revenue is credited to that session's own channel and
campaign. Conversion rate = sessions with a purchase ÷ sessions. Average order value =
revenue ÷ transactions.

## Attribution (`mart_attribution`)

Three models, each crediting exactly the same total revenue and number of conversions:

- **First touch.** The channel that first acquired the user (GA4's user-level
  `traffic_source`).
- **Last touch.** The channel of the session where the purchase happened.
- **Linear.** Revenue split equally across all of the user's sessions up to and including
  the purchase session.

Comparing them shows which channels *introduce* customers (strong in first touch) versus
which *close* them (strong in last touch).

## Expansion / contraction (`mart_user_weekly_revenue`, `mart_user_revenue_trend`)

1. Sum each user's revenue by week. Several purchases in one week, including several on the
   same day, become a single weekly total first.
2. **Safeguard:** only users who purchased in at least two distinct weeks get a trend.
   Everyone else is `Insufficient history`. Without this check, two purchases on the same
   day could be read as a change in spending.
3. Compare each purchasing week with the user's previous purchasing week:
   - more than `TREND_THRESHOLD` (default 10%) higher → **Expansion**
   - more than `TREND_THRESHOLD` lower → **Contraction**
   - otherwise → **Flat**
   - the user's first purchasing week → **Baseline**

Weeks without a purchase are skipped rather than counted as zero, because most e-commerce
customers do not buy every week; treating every gap as a drop to $0 would label nearly
everyone as contracting. Customers who stop buying are captured by the churn flags instead.

## Product affinity (`mart_product_affinity`)

For each ordered pair of products A → B bought in the same transaction:

- **Support** = transactions containing both ÷ all transactions
- **Confidence** = transactions containing both ÷ transactions containing A
- **Lift** = confidence ÷ (transactions containing B ÷ all transactions)

Lift above 1 means the pair is bought together more often than chance. "Bundles" in this
project are an analytical construct built from these pairs, not a field Google published.

## Next category (`mart_next_category`)

For each pair of a customer's consecutive purchases, every category in the earlier purchase
is linked to each category in the later purchase that the earlier one did **not** contain.
Probability = those transitions ÷ consecutive-purchase pairs whose earlier purchase included
the starting category. Results are given for all customers and for each first-touch
acquisition channel. `rank_in_segment = 1` is the recommended next category.

## RFM and churn (`mart_user_rfm_churn`)

The reference date is the last day of the data (`GA4_END_DATE`, 31 Jan 2021).

- **Churned:** no activity of any kind in the last `CHURN_DAYS` days (default 30).
- **Lapsed purchaser:** has bought, but not in the last `CHURN_DAYS` days.
- **RFM scores** (1–5, 5 = best) rank purchasers by recency of last purchase, number of
  transactions and revenue. Ties are broken by user id so results are repeatable.
- **Segments:** Champion (recency ≥ 4 and frequency ≥ 4), Recent customer (recency ≥ 4),
  At-risk high value (frequency or monetary ≥ 4 but not recent), Lapsing customer,
  Non-purchaser.

The data covers only 92 days, so a 30-day window is a short-horizon signal, not a
long-term churn rate.

## Cohort retention (`mart_cohort_retention`)

A user's cohort is the week of their first session in the data. They are retained in week N
if they had any session N weeks after that. Users already active before 1 Nov 2020 appear as
new in the first weeks of the data, so the earliest cohorts are inflated.
