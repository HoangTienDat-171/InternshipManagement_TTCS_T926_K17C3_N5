export const MEETING_TIME_ZONE = 'Asia/Ho_Chi_Minh';

export function meetingDisplayStatus(meeting, now = new Date()) {
  if (meeting?.status === 'CANCELLED') return 'CANCELLED';
  const start = new Date(meeting?.start_at);
  const end = new Date(meeting?.end_at);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 'UPCOMING';
  if (now < start) return 'UPCOMING';
  if (now < end) return 'IN_PROGRESS';
  return 'COMPLETED';
}

const pad = (value) => String(value).padStart(2, '0');

export function getVietnamParts(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: MEETING_TIME_ZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  return Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
}

export function getVietnamDateKey(value) {
  const parts = getVietnamParts(value);
  return parts ? parts.year + '-' + parts.month + '-' + parts.day : '';
}

export function toVietnamDateTimeLocal(value) {
  const parts = getVietnamParts(value);
  return parts ? parts.year + '-' + parts.month + '-' + parts.day + 'T' + parts.hour + ':' + parts.minute : '';
}

export function toVietnamTime(value) {
  const parts = getVietnamParts(value);
  return parts ? parts.hour + ':' + parts.minute : '';
}

export function formatVietnamDateKey(value, options = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return '';
  const date = new Date(value + 'T00:00:00Z');
  return new Intl.DateTimeFormat('vi-VN', { ...options, timeZone: 'UTC' }).format(date);
}

export function composeLocalDateTime(date, time) {
  return date && time ? date + 'T' + time : '';
}

export function addLocalMinutes(value, minutes) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value || '');
  if (!match || !Number.isFinite(Number(minutes))) return '';
  const [, year, month, day, hour, minute] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute) + Number(minutes)));
  return date.getUTCFullYear() + '-' + pad(date.getUTCMonth() + 1) + '-' + pad(date.getUTCDate())
    + 'T' + pad(date.getUTCHours()) + ':' + pad(date.getUTCMinutes());
}

export function localMinuteDifference(start, end) {
  const parse = (value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value || '');
    return match ? Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5])) : NaN;
  };
  return (parse(end) - parse(start)) / 60000;
}

export function toUtcIsoFromVietnamLocal(value) {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})$/.exec(value || '');
  if (!match) return '';
  const date = new Date(match[1] + 'T' + match[2] + ':00+07:00');
  return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}
