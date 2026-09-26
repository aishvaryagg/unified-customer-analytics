# Reporting

The common reporting layer puts GA4 and MIND into one set of tables with the same
definitions, time handling and labels, without merging their people. Three outputs sit on
top of it: Tableau dashboards, Looker Studio, and a Google Sheet with a plain-English summary.

```bash
uca build reporting    # after ga4 and mind; builds the rpt_* tables
uca export-reporting   # optional: CSV copies in target/reporting/ for Tableau
```

## Reporting tables (`sql/reporting/`)

| Table | One row per | Use |
|---|---|---|
| `rpt_kpis` | source × metric | KPI tiles: sessions, orders, revenue, conversion, AOV, churn (GA4); readers, clicks, CTR, disengaged, drifting (MIND). `unit` is `count`, `usd` or `ratio` |
| `rpt_trend_distribution` | source × trend | How many GA4 customers and MIND readers are expanding, contracting or flat, with **shared labels** (`trend`) and the original label (`trend_label`) |
| `rpt_retention_status` | source × population × status | Active / Churned shoppers, Buying recently / Lapsed customers, Engaged / Passive / Disengaged readers |
| `rpt_ga4_weekly_channels` | week × channel | Weekly sessions, orders, revenue and conversion; the top 5 revenue channels plus `Other` |
| `rpt_mind_daily_categories` | day × category | Daily shown, clicks, CTR and readers; the top 6 click categories plus `Other` |

The mart tables (`mart_funnel_daily`, `mart_attribution`, `mart_mind__category_performance`
and the rest) can be added as data sources too.

## Chart rules used throughout

- **One y-axis per chart.** Revenue and conversion rate go in two charts, never a dual axis.
- **At most six series.** Small channels and categories are already folded into `Other`
  in the tables. Colors come from the `UCA Categorical` palette in fixed order, and
  `Other` is always gray. A color stays with its channel when filters change.
- **Labels, not color alone.** Three palette colors are below 3:1 contrast on white, so
  line ends and bars carry direct labels, and each dashboard has a table view.
- **Trend colors carry meaning.** Expansion is blue, Contraction red, Flat and
  Insufficient history gray (`UCA Trend (diverging)`).
- **Filters in one row across the top** (date range, source), not inside chart cards.
- **GA4 and MIND never share an axis or a blended data source.** They sit side by side
  with a caption saying so.

`reporting/tableau/Preferences.tps` holds these palettes. The categorical order was
checked for colorblind separation.

## Tableau

**Connect.** Tableau Desktop connects to BigQuery directly (Connect → Google BigQuery →
your project → `marketing_analytics`). Tableau Public cannot connect to BigQuery, so either
use the CSV files from `uca export-reporting`, or connect Tableau Public to the Google
Sheet below, which holds the same tables.

**Palettes.** Copy `reporting/tableau/Preferences.tps` to `Documents/My Tableau
Repository/Preferences.tps` and restart Tableau.

**Dashboard 1: Marketing performance (GA4)**

| Chart | Data | Form |
|---|---|---|
| KPI row | `rpt_kpis`, source = GA4 | Stat tiles: sessions, orders, revenue, conversion rate, average order value |
| Revenue by week and channel | `rpt_ga4_weekly_channels` | Line chart, one line per channel, labels at line ends |
| Conversion rate by week and channel | `rpt_ga4_weekly_channels` | Separate line chart under the revenue chart |
| Funnel | `mart_funnel_daily` (sum the stage counts) | Horizontal bars, one hue |
| First vs last touch by channel | `mart_attribution` (first_touch, last_touch) | Dumbbell: two shades of one hue per channel |

**Dashboard 2: Content engagement (MIND)**

| Chart | Data | Form |
|---|---|---|
| KPI row | `rpt_kpis`, source = MIND | Stat tiles: readers, clicks, click-through rate, disengaged share |
| Clicks by day and category | `rpt_mind_daily_categories` | Line chart, labels at line ends |
| Click-through rate by category | `mart_mind__category_performance` | Horizontal bars sorted by CTR, one hue |
| Reader status | `rpt_retention_status`, source = MIND | 100% stacked horizontal bar with labels |

**Dashboard 3: Side by side (the common framework)**

| Chart | Data | Form |
|---|---|---|
| Expansion / contraction | `rpt_trend_distribution` | One 100% stacked horizontal bar per source (GA4 customers, MIND readers), ordered by `trend_order`, trend colors, share labels |
| Retention | `rpt_retention_status` | Same form, one bar per source × population |

Caption: *"GA4 (online store, weekly revenue) and MIND (news readers, daily clicks) are
different businesses and people. They share definitions, not customers."*

## Looker Studio

1. Create a report and add a data source: **BigQuery** → your project →
   `marketing_analytics` → `rpt_kpis`. Repeat for each `rpt_*` table (and any marts).
2. Build the same three pages as the Tableau dashboards above. Scorecards map to the
   stat tiles. Set chart colors by dimension value so a channel keeps its color.
3. Do not blend a GA4 table with a MIND table: there is no shared key, by design.
4. Add a date-range control at the top of each page.

Looker Studio queries BigQuery live, so the report updates whenever the tables are rebuilt.

## Google Sheets (non-technical summary)

`reporting/sheets/Code.gs` pulls every `rpt_*` table into its own tab and writes a
**Summary** tab in plain English, for example:

> Online store (GA4, Nov 2020 to Jan 2021): 9 sessions from 4 shoppers produced 6 orders
> and $175 in revenue (conversion rate 66.7%, average order $29.17).

(Numbers from the test data. The real report uses the full dataset.)

Setup:

1. Create a Google Sheet, then **Extensions → Apps Script**.
2. Replace the contents of `Code.gs` with `reporting/sheets/Code.gs`.
3. **Project Settings** → tick *Show "appsscript.json" manifest file*, then replace
   `appsscript.json` with `reporting/sheets/appsscript.json`. This enables the BigQuery
   service. Change `timeZone` to yours so the weekly refresh runs at your local 07:00.
4. **Project Settings → Script properties:** add `GCP_PROJECT` (and `BQ_DATASET` /
   `BQ_LOCATION` if you changed them).
5. Reload the sheet. Use **Marketing report → Refresh now** (approve the permissions the
   first time), then **Refresh every Monday** to schedule it.

The Google account running the script needs permission to run BigQuery jobs in the project
(the *BigQuery Job User* and *BigQuery Data Viewer* roles).

## Testing

`tests/test_reporting.py` builds the reporting tables from the GA4 and MIND test data
and checks every KPI, the shared trend labels, the retention statuses, the `Other`
folding, the CSV export and the Tableau palette file. It also runs the Apps Script
summary code in Node against those same tables, checking the sentences, number formatting
and BigQuery type conversion. The Apps Script BigQuery calls, Tableau and Looker Studio
have not been run against a real account yet.
