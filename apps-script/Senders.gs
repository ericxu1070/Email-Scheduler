function sendOrderReminder(row, csvFormat, bentoBlob) {
  var ctx = buildEmailContext(row, csvFormat);
  var subjectTpl = row.custom_subject || DEFAULT_SUBJECTS[csvFormat];
  var bodyTpl    = row.custom_body    || DEFAULT_BODIES[csvFormat];

  var subject = formatTemplate(subjectTpl, ctx);
  var body    = formatTemplate(bodyTpl,    ctx);

  var htmlBody = _textToHtml(body);
  var options = { name: 'Bentolicious' };

  if (bentoBlob) {
    htmlBody += '<br><img src="cid:bento" alt="Bentolicious" style="max-width:480px;">';
    options.inlineImages = { bento: bentoBlob };
  }
  options.htmlBody = htmlBody;

  GmailApp.sendEmail(row.email, subject, body, options);
}

function sendDanceInvoice(row) {
  var ctx = buildEmailContext(row, 'dance_invoice');
  var subjectTpl = row.custom_subject || DEFAULT_SUBJECTS.dance_invoice;
  var bodyTpl    = row.custom_body    || DEFAULT_BODIES.dance_invoice;

  var subject = formatTemplate(subjectTpl, ctx);
  var body    = formatTemplate(bodyTpl,    ctx);

  GmailApp.sendEmail(row.email, subject, body, { name: 'TVDA admin' });
}

function _textToHtml(text) {
  var escaped = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped.replace(/\n/g, '<br>');
}

function loadBentoBlob() {
  var fileId = readConfig('BENTO_PNG_FILE_ID');
  if (!fileId) return null;
  try {
    return DriveApp.getFileById(fileId).getBlob().setName('bento.png');
  } catch (e) {
    Logger.log('Could not load BENTO_PNG_FILE_ID=' + fileId + ': ' + e);
    return null;
  }
}
