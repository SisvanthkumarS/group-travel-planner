// Display formatting. Ticket-style labels are upper case ("SAT MAR 15 · 18:30").

const pad = (n: number) => String(n).padStart(2, '0');

/**
 * Trip dates are plain calendar dates ("2027-03-14"). `new Date(string)` would
 * read them as UTC midnight and show the previous day west of Greenwich, so
 * build a local date instead.
 */
export function parseDateOnly(value: string): Date {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
}

/** The local calendar date of a timestamp, as "YYYY-MM-DD". */
export function localDateKey(value: Date | string): string {
  const d = typeof value === 'string' ? new Date(value) : value;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const upper = (s: string) => s.toUpperCase();

/** "MAR 14" */
export function shortDate(date: Date): string {
  return upper(
    date
      .toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      .replace(',', ''),
  );
}

/** "MAR 14 → MAR 19" for a trip's date range. */
export function tripDates(start: string, end: string): string {
  return `${shortDate(parseDateOnly(start))} → ${shortDate(parseDateOnly(end))}`;
}

/** "18:30" in the viewer's time zone. */
export function clock(value: Date | string): string {
  const d = typeof value === 'string' ? new Date(value) : value;
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "SAT" */
export function weekday(date: Date): string {
  return upper(date.toLocaleDateString('en-US', { weekday: 'short' }));
}

/** "SAT MAR 15 · 18:30–20:30" (the end date is shown when it differs). */
export function activityWhen(startsAt: string, endsAt: string): string {
  const start = new Date(startsAt);
  const end = new Date(endsAt);
  const day = `${weekday(start)} ${shortDate(start)}`;
  const endPart =
    localDateKey(start) === localDateKey(end)
      ? clock(end)
      : `${weekday(end)} ${shortDate(end)} ${clock(end)}`;
  return `${day} · ${clock(start)}–${endPart}`;
}

/** "1d 04h", "3h 20m", "12m", "closing…" */
export function countdown(deadline: string, now: number = Date.now()): string {
  const ms = new Date(deadline).getTime() - now;
  if (ms <= 0) return 'closing…';
  const minutes = Math.floor(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `${days}d ${pad(hours)}h`;
  if (hours > 0) return `${hours}h ${pad(mins)}m`;
  return `${Math.max(mins, 1)}m`;
}

/** Estimated cost arrives as a decimal string ("45.00"). */
export function money(value: string | number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: n % 1 === 0 ? 0 : 2,
  });
}

/**
 * Value for an <input type="datetime-local"> from a Date, in local time.
 */
export function toDateTimeLocal(date: Date): string {
  return `${localDateKey(date)}T${clock(date)}`;
}

/**
 * The backend requires timezone-aware datetimes. A datetime-local value has no
 * zone, so send it in the viewer's zone with its UTC offset, for example
 * "2027-03-15T20:30:00-04:00". Keeping the offset (instead of converting to Z)
 * lets the backend check trip dates against the traveler's own calendar day.
 */
export function fromDateTimeLocal(value: string): string {
  const date = new Date(value);
  const offset = -date.getTimezoneOffset();
  const abs = Math.abs(offset);
  const zone = `${offset < 0 ? '-' : '+'}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
  return `${localDateKey(date)}T${clock(date)}:${pad(date.getSeconds())}${zone}`;
}

/** Every calendar date from start to end inclusive, as "YYYY-MM-DD". */
export function eachDay(start: string, end: string): string[] {
  const days: string[] = [];
  const d = parseDateOnly(start);
  const last = parseDateOnly(end);
  while (d <= last) {
    days.push(localDateKey(d));
    d.setDate(d.getDate() + 1);
  }
  return days;
}
