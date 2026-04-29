var TICKER_FN = 'sendDue';
var BENTO_FORMATS = ['familymeal', 'wonton'];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Bentolicious')
    .addItem('Import CSV → Family Meal…',   'showImportFamilyMeal')
    .addItem('Import CSV → Wonton…',        'showImportWonton')
    .addItem('Import CSV → Dance Invoice…', 'showImportDanceInvoice')
    .addSeparator()
    .addItem('Send selected rows now',             'sendSelectedNow')
    .addItem('Cancel selected rows',               'cancelSelected')
    .addItem('Refresh send times for selected',    'refreshSelected')
    .addSeparator()
    .addItem('Install 5-minute ticker',            'installTicker')
    .addItem('Remove ticker',                      'removeTicker')
    .addToUi();
}

function readConfig(name) {
  var range = SpreadsheetApp.getActive().getRangeByName(name);
  if (!range) return '';
  var v = range.getValue();
  return v == null ? '' : v;
}

function installTicker() {
  removeTicker();
  var minutes = Number(readConfig('TICKER_MINUTES')) || 5;
  ScriptApp.newTrigger(TICKER_FN).timeBased().everyMinutes(minutes).create();
  SpreadsheetApp.getUi().alert('Ticker installed (every ' + minutes + ' min).');
}

function removeTicker() {
  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === TICKER_FN) {
      ScriptApp.deleteTrigger(triggers[i]);
      removed++;
    }
  }
  if (removed > 0) {
    SpreadsheetApp.getUi().alert('Removed ' + removed + ' ticker trigger(s).');
  }
}

function sendDue() {
  var bentoBlob = loadBentoBlob();
  var now = new Date();
  for (var i = 0; i < BENTO_FORMATS.length; i++) {
    _processDueInSheet(BENTO_FORMATS[i], now, bentoBlob);
  }
}

function _processDueInSheet(csvFormat, now, bentoBlob) {
  var sheetName = SHEET_NAMES[csvFormat];
  var sheet = SpreadsheetApp.getActive().getSheetByName(sheetName);
  if (!sheet) return;
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var headers = SHEET_HEADERS[csvFormat];
  var statusCol  = headers.indexOf('status') + 1;
  var sendCol    = headers.indexOf('send_time') + 1;
  var errorCol   = headers.indexOf('error') + 1;

  var values = sheet.getRange(2, 1, lastRow - 1, headers.length).getValues();
  for (var i = 0; i < values.length; i++) {
    var rowArr = values[i];
    var row = _arrayToRow(rowArr, headers);
    if (row.status !== 'pending') continue;
    if (!row.send_time || !(row.send_time instanceof Date)) continue;
    if (row.send_time.getTime() > now.getTime()) continue;

    var sheetRow = i + 2;
    try {
      sendOrderReminder(row, csvFormat, bentoBlob);
      sheet.getRange(sheetRow, statusCol).setValue('sent');
      sheet.getRange(sheetRow, errorCol).setValue('');
    } catch (e) {
      sheet.getRange(sheetRow, statusCol).setValue('error');
      sheet.getRange(sheetRow, errorCol).setValue(String(e));
      Logger.log('Send failed for ' + sheetName + ' row ' + sheetRow + ': ' + e);
    }
  }
}

function sendSelectedNow() {
  var ctx = _selectionContext();
  if (!ctx) return;
  var bentoBlob = ctx.csvFormat !== 'dance_invoice' ? loadBentoBlob() : null;

  var statusCol = ctx.headers.indexOf('status') + 1;
  var errorCol  = ctx.headers.indexOf('error') + 1;
  var sentAtCol = ctx.headers.indexOf('sent_at') + 1;

  var sent = 0, skipped = 0, failed = 0;
  for (var i = 0; i < ctx.rows.length; i++) {
    var item = ctx.rows[i];
    if (item.row.status !== 'pending') { skipped++; continue; }
    try {
      if (ctx.csvFormat === 'dance_invoice') {
        sendDanceInvoice(item.row);
        if (sentAtCol > 0) ctx.sheet.getRange(item.sheetRow, sentAtCol).setValue(new Date());
      } else {
        sendOrderReminder(item.row, ctx.csvFormat, bentoBlob);
      }
      ctx.sheet.getRange(item.sheetRow, statusCol).setValue('sent');
      ctx.sheet.getRange(item.sheetRow, errorCol).setValue('');
      sent++;
    } catch (e) {
      ctx.sheet.getRange(item.sheetRow, statusCol).setValue('error');
      ctx.sheet.getRange(item.sheetRow, errorCol).setValue(String(e));
      failed++;
    }
  }
  SpreadsheetApp.getUi().alert(
    'Sent: ' + sent + '   Skipped (not pending): ' + skipped + '   Failed: ' + failed
  );
}

function cancelSelected() {
  var ctx = _selectionContext();
  if (!ctx) return;
  var statusCol = ctx.headers.indexOf('status') + 1;
  var n = 0;
  for (var i = 0; i < ctx.rows.length; i++) {
    if (ctx.rows[i].row.status !== 'pending') continue;
    ctx.sheet.getRange(ctx.rows[i].sheetRow, statusCol).setValue('cancelled');
    n++;
  }
  SpreadsheetApp.getUi().alert('Cancelled ' + n + ' pending row(s).');
}

function refreshSelected() {
  var ctx = _selectionContext();
  if (!ctx) return;
  if (ctx.csvFormat === 'dance_invoice') {
    SpreadsheetApp.getUi().alert('Dance invoices send immediately on import; nothing to refresh.');
    return;
  }
  var leadHours = Number(readConfig('LEAD_HOURS')) || 4;
  var sendCol  = ctx.headers.indexOf('send_time') + 1;
  var errorCol = ctx.headers.indexOf('error') + 1;
  var n = 0;
  for (var i = 0; i < ctx.rows.length; i++) {
    var row = ctx.rows[i].row;
    if (row.status !== 'pending') continue;
    var pickupTime = parsePickupTime(row.pickup_time, ctx.csvFormat);
    if (!pickupTime) {
      ctx.sheet.getRange(ctx.rows[i].sheetRow, errorCol).setValue('invalid pickup_time');
      continue;
    }
    var pickupDate = parseDateFromItemName(row.item_name);
    var sendTime = computeSendTime(pickupDate, pickupTime, leadHours);
    ctx.sheet.getRange(ctx.rows[i].sheetRow, sendCol).setValue(sendTime);
    ctx.sheet.getRange(ctx.rows[i].sheetRow, errorCol).setValue('');
    n++;
  }
  SpreadsheetApp.getUi().alert('Refreshed ' + n + ' pending row(s).');
}

function _selectionContext() {
  var ui = SpreadsheetApp.getUi();
  var sheet = SpreadsheetApp.getActiveSheet();
  var name = sheet.getName();
  var csvFormat = null;
  for (var key in SHEET_NAMES) {
    if (SHEET_NAMES[key] === name) { csvFormat = key; break; }
  }
  if (!csvFormat) {
    ui.alert('Run this from one of: ' + Object.keys(SHEET_NAMES).map(function(k){return SHEET_NAMES[k];}).join(', '));
    return null;
  }
  var headers = SHEET_HEADERS[csvFormat];
  var rangeList = sheet.getActiveRangeList();
  if (!rangeList) {
    ui.alert('Select one or more rows first.');
    return null;
  }
  var ranges = rangeList.getRanges();
  var rowSet = {};
  for (var i = 0; i < ranges.length; i++) {
    var r = ranges[i];
    for (var rr = r.getRow(); rr <= r.getLastRow(); rr++) {
      if (rr === 1) continue;
      rowSet[rr] = true;
    }
  }
  var sheetRows = Object.keys(rowSet).map(Number).sort(function(a,b){return a-b;});
  if (sheetRows.length === 0) {
    ui.alert('Select one or more data rows (not the header).');
    return null;
  }
  var rows = [];
  for (var j = 0; j < sheetRows.length; j++) {
    var sr = sheetRows[j];
    var arr = sheet.getRange(sr, 1, 1, headers.length).getValues()[0];
    rows.push({ sheetRow: sr, row: _arrayToRow(arr, headers) });
  }
  return { sheet: sheet, csvFormat: csvFormat, headers: headers, rows: rows };
}

function _arrayToRow(arr, headers) {
  var o = {};
  for (var i = 0; i < headers.length; i++) o[headers[i]] = arr[i];
  return o;
}
