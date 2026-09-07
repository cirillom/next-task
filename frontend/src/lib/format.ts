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
