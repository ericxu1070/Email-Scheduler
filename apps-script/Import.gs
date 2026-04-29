var SHEET_NAMES = {
  familymeal:    'FamilyMeal',
  wonton:        'Wonton',
  dance_invoice: 'DanceInvoice'
};

var SHEET_HEADERS = {
  familymeal: ['email','order_number','pickup_time','item_name','full_name','custom_subject','custom_body','send_time','status','error'],
  wonton:     ['email','order_number','pickup_time','item_name','full_name','custom_subject','custom_body','send_time','status','error'],
  dance_invoice: ['email','invoice_num','student_name','invoice_desp','parent_name','total','invoice_url','custom_subject','custom_body','sent_at','status','error']
};

var COLUMN_MAPPINGS = {
  familymeal: {
    email:        'Email',
    order_number: 'Order Number',
    pickup_time:  'Pick Up',
    item_name:    'Item Name',
    full_name:    'Full Name'
  },
  wonton: {
    email:        'Billing: E-mail Address',
    order_number: 'Purchase ID',
    pickup_time:  'PU Time',
    item_name:    'Order Items: Category',
    full_name:    'Billing: Full Name'
  },
  dance_invoice: {
    email:        'Email',
    order_number: 'invoice_num',
    pickup_time:  'Student_Name',
    item_name:    'Invoice desp',
    full_name:    'Parent Name',
    total:        'total',
    invoice_url:  'Invoice URL'
  }
};

function showImportDialog(csvFormat) {
  var template = HtmlService.createTemplateFromFile('Picker');
  template.csvFormat = csvFormat;
  template.formatLabel = SHEET_NAMES[csvFormat];
  var html = template.evaluate().setWidth(420).setHeight(420);
  SpreadsheetApp.getUi().showModalDialog(html, 'Import ' + SHEET_NAMES[csvFormat] + ' CSV');
}

function showImportFamilyMeal()   { showImportDialog('familymeal'); }
function showImportWonton()       { showImportDialog('wonton'); }
function showImportDanceInvoice() { showImportDialog('dance_invoice'); }

function importRows(csvFormat, csvText, customSubject, customBody) {
  var rows = Utilities.parseCsv(csvText);
  if (!rows || rows.length < 2) {
    return { inserted: 0, errors: ['CSV is empty or has no data rows.'] };
  }
  var header = rows[0];
  var mapping = COLUMN_MAPPINGS[csvFormat];
  if (!mapping) return { inserted: 0, errors: ['Unknown format: ' + csvFormat] };

  var colIdx = {};
  for (var key in mapping) {
    var idx = header.indexOf(mapping[key]);
    if (idx === -1) {
      return { inserted: 0, errors: ['Missing required column: ' + mapping[key]] };
    }
    colIdx[key] = idx;
  }
  var sheet = _ensureSheet(csvFormat);
  var leadHours = Number(readConfig('LEAD_HOURS')) || 4;
  var bentoBlob = (csvFormat !== 'dance_invoice') ? loadBentoBlob() : null;

  var inserted = 0;
  var errors = [];

  for (var r = 1; r < rows.length; r++) {
    var raw = rows[r];
    if (!raw || raw.length === 0 || raw.every(function(c) { return !c; })) continue;

    try {
      var row = {
        email:        raw[colIdx.email],
        order_number: raw[colIdx.order_number],
        pickup_time:  raw[colIdx.pickup_time],
        item_name:    raw[colIdx.item_name],
        full_name:    raw[colIdx.full_name],
        custom_subject: customSubject || '',
        custom_body:    customBody || ''
      };

      if (csvFormat === 'dance_invoice') {
        row.total       = raw[colIdx.total];
        row.invoice_url = raw[colIdx.invoice_url];
        try {
          sendDanceInvoice(row);
          _appendRow(sheet, csvFormat, row, { status: 'sent', sent_at: new Date(), error: '' });
          inserted++;
        } catch (e) {
          _appendRow(sheet, csvFormat, row, { status: 'error', sent_at: '', error: String(e) });
          errors.push('Row ' + (r + 1) + ' send failed: ' + e);
        }
        continue;
      }

      var pickupTime = parsePickupTime(row.pickup_time, csvFormat);
      if (!pickupTime) {
        errors.push('Row ' + (r + 1) + ': could not parse pickup_time "' + row.pickup_time + '"');
        _appendRow(sheet, csvFormat, row, { status: 'error', send_time: '', error: 'invalid pickup_time' });
        continue;
      }
      var pickupDate = parseDateFromItemName(row.item_name);
      var sendTime = computeSendTime(pickupDate, pickupTime, leadHours);

      _appendRow(sheet, csvFormat, row, { status: 'pending', send_time: sendTime, error: '' });
      inserted++;
    } catch (e) {
      errors.push('Row ' + (r + 1) + ': ' + e);
    }
  }

  return { inserted: inserted, errors: errors };
}

function _ensureSheet(csvFormat) {
  var ss = SpreadsheetApp.getActive();
  var name = SHEET_NAMES[csvFormat];
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(SHEET_HEADERS[csvFormat]);
    sheet.setFrozenRows(1);
  } else if (sheet.getLastRow() === 0) {
    sheet.appendRow(SHEET_HEADERS[csvFormat]);
    sheet.setFrozenRows(1);
  }
  var headers = SHEET_HEADERS[csvFormat];
  var ptIdx = headers.indexOf('pickup_time');
  if (ptIdx !== -1) {
    sheet.getRange(1, ptIdx + 1, sheet.getMaxRows(), 1).setNumberFormat('@');
  }
  return sheet;
}

function _appendRow(sheet, csvFormat, row, extras) {
  var headers = SHEET_HEADERS[csvFormat];
  var combined = {};
  for (var k in row) combined[k] = row[k];
  for (var k2 in extras) combined[k2] = extras[k2];
  var out = headers.map(function(h) { return combined[h] != null ? combined[h] : ''; });
  sheet.appendRow(out);
}
