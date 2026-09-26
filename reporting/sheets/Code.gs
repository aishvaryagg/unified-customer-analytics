/**
 * Marketing report for Google Sheets.
 *
 * Pulls the rpt_* tables from BigQuery into tabs of this spreadsheet and writes a
 * plain-English Summary tab for non-technical readers. Setup: docs/reporting.md.
 *
 * Script properties (Project Settings > Script properties):
 *   GCP_PROJECT  required, the Google Cloud project with the tables
 *   BQ_DATASET   optional, default "marketing_analytics"
 *   BQ_LOCATION  optional, default "US"
 */

var REPORT_TABLES = [
  'rpt_kpis',
  'rpt_trend_distribution',
  'rpt_retention_status',
  'rpt_ga4_weekly_channels',
  'rpt_mind_daily_categories',
];

var NUMERIC_TYPES = ['INTEGER', 'INT64', 'FLOAT', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Marketing report')
    .addItem('Refresh now', 'refreshReport')
    .addItem('Refresh every Monday', 'scheduleWeeklyRefresh')
    .addToUi();
}

function getConfig_() {
  var props = PropertiesService.getScriptProperties();
  var project = props.getProperty('GCP_PROJECT');
  if (!project) {
    throw new Error('Set the GCP_PROJECT script property (Project Settings > Script properties).');
  }
  return {
    project: project,
    dataset: props.getProperty('BQ_DATASET') || 'marketing_analytics',
    location: props.getProperty('BQ_LOCATION') || 'US',
  };
}

function refreshReport() {
  var config = getConfig_();
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var data = {};
  REPORT_TABLES.forEach(function (table) {
    var sql = 'SELECT * FROM `' + config.project + '.' + config.dataset + '.' + table + '`';
    var result = runQuery_(config, sql);
    data[table] = result.records;
    writeTable_(spreadsheet, table, result.headers, result.rows);
  });
  var lines = buildSummary(data.rpt_kpis, data.rpt_trend_distribution, data.rpt_retention_status);
  writeSummary_(spreadsheet, lines, new Date());
}

function scheduleWeeklyRefresh() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (trigger.getHandlerFunction() === 'refreshReport') ScriptApp.deleteTrigger(trigger);
  });
  ScriptApp.newTrigger('refreshReport').timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(7).create();
  SpreadsheetApp.getActiveSpreadsheet().toast('The report will refresh every Monday at about 07:00.');
}

function runQuery_(config, sql) {
  var request = { query: sql, useLegacySql: false, location: config.location, timeoutMs: 60000 };
  var response = BigQuery.Jobs.query(request, config.project);
  var jobId = response.jobReference.jobId;
  var options = { location: config.location };
  while (!response.jobComplete) {
    Utilities.sleep(1000);
    response = BigQuery.Jobs.getQueryResults(config.project, jobId, options);
  }
  var rows = (response.rows || []).slice();
  var pageToken = response.pageToken;
  while (pageToken) {
    var page = BigQuery.Jobs.getQueryResults(config.project, jobId, {
      location: config.location,
      pageToken: pageToken,
    });
    rows = rows.concat(page.rows || []);
    pageToken = page.pageToken;
  }
  return toRecords(response.schema.fields, rows);
}

/** BigQuery returns every cell as a string; convert by column type. */
function convertValue(value, type) {
  if (value === null || value === undefined) return null;
  if (NUMERIC_TYPES.indexOf(type) >= 0) return Number(value);
  if (type === 'BOOLEAN' || type === 'BOOL') return value === 'true';
  return value;
}

function toRecords(fields, rawRows) {
  var headers = fields.map(function (field) { return field.name; });
  var rows = rawRows.map(function (row) {
    return row.f.map(function (cell, i) { return convertValue(cell.v, fields[i].type); });
  });
  var records = rows.map(function (row) {
    var record = {};
    headers.forEach(function (name, i) { record[name] = row[i]; });
    return record;
  });
  return { headers: headers, rows: rows, records: records };
}

function writeTable_(spreadsheet, name, headers, rows) {
  var sheet = spreadsheet.getSheetByName(name) || spreadsheet.insertSheet(name);
  sheet.clear();
  var values = [headers].concat(rows.map(function (row) {
    return row.map(function (v) { return v === null ? '' : v; });
  }));
  sheet.getRange(1, 1, values.length, headers.length).setValues(values);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
}

function writeSummary_(spreadsheet, lines, updatedAt) {
  var sheet = spreadsheet.getSheetByName('Summary') || spreadsheet.insertSheet('Summary', 0);
  sheet.clear();
  var values = [['Marketing report'], ['Updated ' + updatedAt.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'], ['']]
    .concat(lines.map(function (line) { return [line]; }));
  sheet.getRange(1, 1, values.length, 1).setValues(values).setWrap(true).setVerticalAlignment('top');
  sheet.getRange(1, 1).setFontSize(16).setFontWeight('bold');
  sheet.getRange(2, 1).setFontColor('#52514e');
  sheet.setColumnWidth(1, 720);
}

// ---- Plain-English summary (pure functions, tested in tests/test_reporting.py) ----

function withCommas_(text) {
  return text.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function fmtCount(value) {
  return withCommas_(String(Math.round(value)));
}

function fmtUsd(value, decimals) {
  var parts = Number(value).toFixed(decimals || 0).split('.');
  return '$' + withCommas_(parts[0]) + (parts.length > 1 ? '.' + parts[1] : '');
}

function fmtPct(value) {
  return (value * 100).toFixed(1) + '%';
}

function metricMap_(kpis) {
  var map = {};
  (kpis || []).forEach(function (row) { map[row.source + '.' + row.metric] = row.value; });
  return map;
}

function peopleBy_(rows, source, key) {
  var map = {};
  (rows || []).forEach(function (row) {
    if (row.source === source) map[row[key]] = (map[row[key]] || 0) + row.people;
  });
  return map;
}

function trendLine_(counts, who, rising, falling) {
  var withTrend = (counts.Expansion || 0) + (counts.Contraction || 0) + (counts.Flat || 0);
  if (!withTrend) return null;
  return 'Of ' + who + ' with at least two active periods, ' + fmtCount(counts.Expansion || 0) +
    ' ' + rising + ', ' + fmtCount(counts.Contraction || 0) + ' ' + falling + ' and ' +
    fmtCount(counts.Flat || 0) + ' held flat; ' + fmtCount(counts['Insufficient history'] || 0) +
    ' had too little history to judge.';
}

function buildSummary(kpis, trends, retention) {
  var m = metricMap_(kpis);
  var lines = [];
  if (m['GA4.sessions'] !== undefined) {
    lines.push('Online store (GA4, Nov 2020 to Jan 2021): ' + fmtCount(m['GA4.sessions']) +
      ' sessions from ' + fmtCount(m['GA4.users']) + ' shoppers produced ' +
      fmtCount(m['GA4.transactions']) + ' orders and ' + fmtUsd(m['GA4.revenue_usd']) +
      ' in revenue (conversion rate ' + fmtPct(m['GA4.conversion_rate']) + ', average order ' +
      fmtUsd(m['GA4.avg_order_value_usd'], 2) + ').');
    lines.push(fmtCount(m['GA4.customers']) + ' shoppers bought something; ' +
      fmtPct(m['GA4.lapsed_customer_share']) + ' of those customers had not ordered again by the end ' +
      'of the data, and ' + fmtPct(m['GA4.churned_share']) + ' of all shoppers had gone quiet.');
  }
  var ga4Trend = trendLine_(peopleBy_(trends, 'GA4', 'trend'), 'GA4 customers',
    'spent more week over week', 'spent less');
  if (ga4Trend) lines.push(ga4Trend);
  if (m['MIND.readers'] !== undefined) {
    lines.push('News readers (MIND, one week in Nov 2019): ' + fmtCount(m['MIND.readers']) +
      ' readers saw ' + fmtCount(m['MIND.impressions']) + ' impressions and clicked ' +
      fmtCount(m['MIND.clicks']) + ' articles (click-through rate ' + fmtPct(m['MIND.click_through_rate']) + ').');
  }
  var mindTrend = trendLine_(peopleBy_(trends, 'MIND', 'trend'), 'MIND readers',
    'clicked more day over day', 'clicked less');
  if (mindTrend) lines.push(mindTrend);
  if (m['MIND.disengaged_share'] !== undefined) {
    lines.push(fmtPct(m['MIND.disengaged_share']) + ' of readers had disengaged and ' +
      fmtPct(m['MIND.passive_share']) + ' were still visiting without clicking; ' +
      fmtCount(m['MIND.drifting_readers']) +
      (m['MIND.drifting_readers'] === 1 ? ' reader was' : ' readers were') +
      ' drifting away from a topic they used to read.');
  }
  if (lines.length) {
    lines.push('GA4 and MIND are different businesses and different people, so their figures are ' +
      'shown side by side and never combined. MIND has no revenue data.');
  }
  return lines;
}

if (typeof module !== 'undefined') {
  module.exports = { buildSummary: buildSummary, toRecords: toRecords, convertValue: convertValue,
    fmtUsd: fmtUsd, fmtPct: fmtPct, fmtCount: fmtCount };
}
