var TZ = 'America/Los_Angeles';

function parsePickupTime(pickupStr, csvFormat) {
  if (!pickupStr || typeof pickupStr !== 'string') return null;
  var s = pickupStr.trim().toUpperCase();
  if (csvFormat === 'wonton') {
    s = s.replace(/^(DINNER|LUNCH):/i, '').trim();
    if (s.indexOf('-') !== -1) s = s.split('-')[0].trim();
  }
  s = s.replace(/(\d)([AP]M)/g, '$1 $2');
  s = s.replace(/[^0-9: AMPM]/g, '');
  s = s.trim().replace(/\s+/g, ' ');

  var m = s.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/);
  if (!m) m = s.match(/^(\d{1,2})()\s*(AM|PM)$/);
  if (!m) {
    var hourOnly = s.match(/^(\d{1,2})\s*(AM|PM)$/);
    if (hourOnly) {
      m = [hourOnly[0], hourOnly[1], '00', hourOnly[2]];
    }
  }
  if (!m) return null;

  var hour = parseInt(m[1], 10);
  var minute = m[2] === '' ? 0 : parseInt(m[2], 10);
  var ampm = m[3];
  if (isNaN(hour) || isNaN(minute) || hour < 1 || hour > 12 || minute < 0 || minute > 59) return null;
  if (ampm === 'PM' && hour !== 12) hour += 12;
  if (ampm === 'AM' && hour === 12) hour = 0;
  return { hours: hour, minutes: minute };
}

function parseDateFromItemName(itemName) {
  var today = new Date();
  if (!itemName || typeof itemName !== 'string') return _todayInTz();
  var match = itemName.match(/(\d{1,2})\/(\d{1,2})(\/(\d{4}))?/);
  if (!match) return _todayInTz();
  var month = parseInt(match[1], 10);
  var day = parseInt(match[2], 10);
  var year = match[4] ? parseInt(match[4], 10) : parseInt(Utilities.formatDate(today, TZ, 'yyyy'), 10);
  return { year: year, month: month, day: day };
}

function _todayInTz() {
  var now = new Date();
  return {
    year: parseInt(Utilities.formatDate(now, TZ, 'yyyy'), 10),
    month: parseInt(Utilities.formatDate(now, TZ, 'M'), 10),
    day: parseInt(Utilities.formatDate(now, TZ, 'd'), 10)
  };
}

function formatPickupTime(pickupStr) {
  if (!pickupStr) return '';
  var s = String(pickupStr).trim().toUpperCase();
  s = s.replace(/(\d)([AP]M)/g, '$1 $2').replace(/\s+/g, ' ');
  if (s.indexOf('-') !== -1) s = s.split('-')[0].trim();
  var m = s.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/);
  if (!m) return pickupStr;
  var h = parseInt(m[1], 10);
  var min = m[2];
  return h + ':' + min + ' ' + m[3];
}

function computeSendTime(dateParts, timeParts, leadHours) {
  var iso = Utilities.formatString(
    '%04d-%02d-%02d %02d:%02d:00',
    dateParts.year, dateParts.month, dateParts.day, timeParts.hours, timeParts.minutes
  );
  var pickup = Utilities.parseDate(iso, TZ, 'yyyy-MM-dd HH:mm:ss');
  return new Date(pickup.getTime() - leadHours * 3600 * 1000);
}

function nowInTz() {
  return new Date();
}
