const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const DAY_MS = 86_400_000;

const dateFormatter = new Intl.DateTimeFormat('pt-BR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric'
});

const dateTimeFormatter = new Intl.DateTimeFormat('pt-BR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23'
});

export function formatDate(value: string | Date): string {
  if (typeof value === 'string') {
    const match = DATE_ONLY_PATTERN.exec(value);
    if (match) return `${match[3]}/${match[2]}/${match[1]}`;
  }

  return dateFormatter.format(value instanceof Date ? value : new Date(value));
}

export function formatDateTime(value: string | Date): string {
  return dateTimeFormatter.format(value instanceof Date ? value : new Date(value));
}

// Local calendar values are for controls and due dates; timestamps travel as UTC ISO strings.
export function localDateTime(value: string | Date = new Date()): string {
  const date = value instanceof Date ? value : new Date(value);
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${String(date.getFullYear()).padStart(4, '0')}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function localDate(value: string | Date = new Date()): string {
  return localDateTime(value).slice(0, 10);
}

export function formatDateInput(value: string, includeTime = false): string {
  if (!value) return '';
  return formatDate(value.slice(0, 10)) + (includeTime ? ` ${value.slice(11, 16)}` : '');
}

// Return null for invalid/incomplete input, and an empty string when cleared.
export function parseDateInput(value: string, includeTime = false): string | null {
  if (!value) return '';
  const match = (includeTime
    ? /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/
    : /^(\d{2})\/(\d{2})\/(\d{4})$/).exec(value);
  if (!match) return null;
  const [, day, month, year, hour = '00', minute = '00'] = match;
  if (+year < 1 || +hour > 23 || +minute > 59) return null;
  const isoDate = `${year}-${month}-${day}`;
  // Validate calendar dates independently of timezone (including skipped local days).
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== isoDate) return null;
  if (!includeTime) return isoDate;
  const local = `${isoDate}T${hour}:${minute}`;
  // Reject nonexistent wall times during a daylight-saving jump instead of shifting them.
  return localDateTime(new Date(local)) === local ? local : null;
}

export function dateInputError(value: string, includeTime = false, min = ''): string {
  const parsed = parseDateInput(value, includeTime);
  if (parsed === null) return `Enter a valid ${includeTime ? 'local date and time as dd/mm/yyyy HH:mm (00:00–23:59)' : 'date as dd/mm/yyyy'}.`;
  if (parsed && min && parsed < min) return `Enter ${formatDateInput(min, includeTime)} or later.`;
  return '';
}

export function daysSince(value: string | Date, now = Date.now()): number {
  const timestamp = value instanceof Date ? value.getTime() : new Date(value).getTime();
  return Math.max(0, Math.floor((now - timestamp) / DAY_MS));
}

export function formatRelativeTime(value: string | Date, now = Date.now()): string {
  const timestamp = value instanceof Date ? value.getTime() : new Date(value).getTime();
  const seconds = Math.max(0, Math.floor((now - timestamp) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
