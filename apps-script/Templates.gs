var DEFAULT_SUBJECTS = {
  familymeal: '[Bentolicious] {item_name} Pick Up Reminder (Order #{order_number})',
  wonton:     '[Bentolicious] {item_name} Pick Up Reminder (Order #{order_number})',
  dance_invoice: '[TVDA] {invoice_desp}_{student_name}_#({invoice_num})'
};

var DEFAULT_BODIES = {
  familymeal:
    'Hi {full_name},\n\n' +
    'This is a friendly reminder that your order \'{item_name}\' is scheduled for pickup at {pickup_time} on {pickup_date}.\n\n' +
    'See you soon!\n\n' +
    'Bentolicious Team\n\n' +
    'Pick-up location: Bentolicious — 4833 Hopyard Road, E#3, Pleasanton\n' +
    '(Back side of the plaza near Chabot Drive.)\n',

  wonton:
    'Hi {full_name},\n\n' +
    'This is a friendly reminder for your wonton order, scheduled for pickup around {pickup_time} on {pickup_date}.\n\n' +
    'See you soon!\n\n' +
    'Bentolicious Team\n\n' +
    'Pick-up location: Bentolicious — 4833 Hopyard Road, E#3, Pleasanton\n' +
    '(Back side of the plaza near Chabot Drive.)\n',

  dance_invoice:
    'Dear {parent_name},\n\n' +
    'Attached, please find {student_name}\'s {invoice_desp} in the amount of {total}:\n\n' +
    '{invoice_url}\n\n' +
    'Payment is due upon receipt.\n\n' +
    'Payment method:\n' +
    '- Zelle: 510-988-8666\n' +
    '- PayPal: 510-988-8666\n' +
    '- Check pay to the order of Tri-Valley Dance Academy \n' +
    '- Cash\n\n' +
    'Please include invoice # {invoice_num} in the payment memo.\n\n' +
    'Thanks for your attention.\n\n' +
    'Best regards,\n\n' +
    'TVDA admin'
};

function formatTemplate(template, ctx) {
  return template.replace(/\{(\w+)\}/g, function(_, key) {
    return ctx[key] != null ? String(ctx[key]) : '';
  });
}

function buildEmailContext(row, csvFormat) {
  var firstName = row.full_name ? String(row.full_name).split(/\s+/)[0] : '';
  var pickupDate = '';
  if (csvFormat !== 'dance_invoice' && row.item_name) {
    pickupDate = formatPickupDate(parseDateFromItemName(row.item_name));
  }

  var ctx = {
    full_name:    firstName,
    parent_name:  firstName,
    order_number: row.order_number || '',
    item_name:    row.item_name || '',
    pickup_time:  formatPickupTime(row.pickup_time),
    pickup_date:  pickupDate,
    date_str:     pickupDate,
    student_name: '',
    invoice_num:  row.order_number || '',
    invoice_desp: row.item_name || '',
    total:        row.total || '',
    invoice_url:  row.invoice_url || ''
  };

  if (csvFormat === 'dance_invoice') {
    ctx.student_name = row.pickup_time || '';
    ctx.invoice_desp = row.item_name || '';
  }

  return ctx;
}
