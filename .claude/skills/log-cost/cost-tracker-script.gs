/**
 * Cost tracker web endpoint. Paste into the Google Sheet: Extensions > Apps Script.
 * Claude posts JSON here to add or change costs; the sheet's own formulas do the totals.
 *
 * Every request must carry the secret token below. Change it before deploying and
 * put the same value in ~/.produkto-cost-tracker (see SKILL.md).
 */
const TOKEN = 'CHANGE-ME';

const SUBS = 'Subscriptions';
const USAGE = 'API & Usage Costs';
const FORECAST = 'Forecast';

function doPost(e) {
  try {
    const req = JSON.parse(e.postData.contents);
    if (req.token !== TOKEN) return out({ ok: false, error: 'bad token' });
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    switch (req.action) {
      case 'read': return out({ ok: true, data: readAll(ss) });
      case 'add_subscription': return out(addSubscription(ss, req.row));
      case 'add_usage': return out(addUsage(ss, req.row));
      case 'update_subscription': return out(updateSubscription(ss, req.tool, req.fields));
      case 'set_forecast': return out(setForecast(ss, req.cost, req.month, req.value, req.note));
      case 'write_sheet': return out(writeSheet(ss, req.name, req.cells, req.widths));
      default: return out({ ok: false, error: 'unknown action ' + req.action });
    }
  } catch (err) {
    return out({ ok: false, error: String(err) });
  }
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** Replace a whole tab with a grid of values (strings starting "=" become formulas). Setup only. */
function writeSheet(ss, name, cells, widths) {
  let sh = ss.getSheetByName(name) || ss.insertSheet(name);
  sh.clear();
  const w = Math.max.apply(null, cells.map(function (r) { return r.length; }));
  const grid = cells.map(function (r) { while (r.length < w) r.push(''); return r; });
  sh.getRange(1, 1, grid.length, w).setValues(grid);
  sh.getRange(1, 1, 1, w).setFontWeight('bold');
  (widths || []).forEach(function (px, i) { if (px) sh.setColumnWidth(i + 1, px); });
  const def = ss.getSheetByName('Sheet1');
  if (def && ss.getSheets().length > 1 && def.getLastRow() === 0) ss.deleteSheet(def);
  return { ok: true, rows: grid.length };
}

function readAll(ss) {
  const res = {};
  ss.getSheets().forEach(function (sh) {
    res[sh.getName()] = sh.getDataRange().getDisplayValues();
  });
  return res;
}

/** Row number holding `label` in `col` (1-based), or -1. */
function findRow(sh, col, label) {
  const vals = sh.getRange(1, col, sh.getLastRow(), 1).getValues();
  for (let i = 0; i < vals.length; i++) {
    if (String(vals[i][0]).trim().toLowerCase() === String(label).trim().toLowerCase()) return i + 1;
  }
  return -1;
}

/** Last row with something in column A above `beforeRow`. */
function lastFilled(sh, beforeRow) {
  const vals = sh.getRange(1, 1, beforeRow - 1, 1).getValues();
  for (let i = vals.length - 1; i >= 0; i--) if (vals[i][0] !== '') return i + 1;
  return 1;
}

function monthlyFormula(r) {
  return '=IF(E' + r + '="","",IF(D' + r + '="Yearly",E' + r + '/12,IF(D' + r + '="Quarterly",E' + r + '/3,E' + r + '))*IF(F' + r + '="EUR",$G$' + '__RATE__' + ',1))';
}

// row: {tool, purpose, plan, cycle, amount, currency, started, renews, status, notes}
function addSubscription(ss, row) {
  const sh = ss.getSheetByName(SUBS);
  if (findRow(sh, 1, row.tool) > 0) return { ok: false, error: row.tool + ' already exists; use update_subscription' };
  const totalRow = findRow(sh, 4, 'Total per month');
  const at = lastFilled(sh, totalRow) + 1;
  if (at >= totalRow) sh.insertRowBefore(totalRow);
  const rateRow = findRow(sh, 4, 'EUR to USD rate');
  sh.getRange(at, 1, 1, 11).setValues([[
    row.tool, row.purpose || '', row.plan || '', row.cycle || 'Monthly', row.amount === undefined ? '' : row.amount,
    row.currency || 'USD', '', row.started || '', row.renews || '', row.status || 'Active', row.notes || ''
  ]]);
  sh.getRange(at, 7).setFormula(monthlyFormula(at).replace('__RATE__', rateRow));
  fixSubTotals(sh);
  return { ok: true, row: at };
}

function updateSubscription(ss, tool, fields) {
  const sh = ss.getSheetByName(SUBS);
  const r = findRow(sh, 1, tool);
  if (r < 0) return { ok: false, error: tool + ' not found' };
  const cols = { purpose: 2, plan: 3, cycle: 4, amount: 5, currency: 6, started: 8, renews: 9, status: 10, notes: 11 };
  Object.keys(fields).forEach(function (k) {
    if (cols[k]) sh.getRange(r, cols[k]).setValue(fields[k]);
  });
  return { ok: true, row: r };
}

/** Keep the total and missing-count formulas covering every subscription row. */
function fixSubTotals(sh) {
  const totalRow = findRow(sh, 4, 'Total per month');
  const last = lastFilled(sh, totalRow);
  sh.getRange(totalRow, 7).setFormula('=SUMIF(J2:J' + last + ',"Active",G2:G' + last + ')');
  const missRow = findRow(sh, 4, 'Amounts still missing');
  if (missRow > 0) sh.getRange(missRow, 7).setFormula('=COUNTIFS(J2:J' + last + ',"Active",E2:E' + last + ',"")');
}

// row: {date (yyyy-mm-dd), provider, what, amount (USD), type: Usage|Top-up|One-off|Credit, source, notes}
function addUsage(ss, row) {
  const sh = ss.getSheetByName(USAGE);
  const totalRow = findRow(sh, 3, 'Total logged');
  const at = lastFilled(sh, totalRow) + 1;
  if (at >= totalRow - 1) sh.insertRowsBefore(totalRow, 1);
  const tRow = findRow(sh, 3, 'Total logged');
  sh.getRange(at, 1, 1, 7).setValues([[
    row.date, row.provider, row.what || '', row.amount, row.type || 'Usage', row.source || 'Kelian, in chat', row.notes || ''
  ]]);
  sh.getRange(at, 1).setNumberFormat('@').setValue(row.date);
  const last = lastFilled(sh, tRow);
  sh.getRange(tRow, 4).setFormula('=SUM(D2:D' + last + ')');
  sh.getRange(tRow + 1, 4).setFormula('=SUMIF(E2:E' + last + ',"Top-up",D2:D' + last + ')');
  sh.getRange(tRow + 2, 4).setFormula('=SUMIF(E2:E' + last + ',"Usage",D2:D' + last + ')');
  return { ok: true, row: at };
}

/** Set one forecast cell. month like "2026-11". Adds the cost line if it is new. */
function setForecast(ss, cost, month, value, note) {
  const sh = ss.getSheetByName(FORECAST);
  const header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(String);
  let col = header.indexOf(month) + 1;
  if (col < 1) return { ok: false, error: 'month ' + month + ' not in Forecast' };
  let r = findRow(sh, 1, cost);
  if (r < 0) {
    const totalRow = findRow(sh, 1, 'Total forecast (USD)');
    sh.insertRowBefore(totalRow - 1);
    r = totalRow - 1;
    sh.getRange(r, 1, 1, 2).setValues([[cost, 'Estimate']]);
    for (let c = 3; c < header.indexOf('Notes') + 1; c++) sh.getRange(r, c).setValue(0);
    const t = findRow(sh, 1, 'Total forecast (USD)');
    for (let c = 3; c < header.indexOf('Notes') + 1; c++) {
      const L = String.fromCharCode(64 + c);
      sh.getRange(t, c).setFormula('=SUM(' + L + '2:' + L + (t - 2) + ')');
    }
  }
  sh.getRange(r, col).setValue(value);
  if (note) sh.getRange(r, header.indexOf('Notes') + 1).setValue(note);
  return { ok: true, row: r };
}
