// Display formatting. Ticket-style labels are upper case ("SAT MAR 15 · 18:30").
//
// Times inside a trip are shown in the trip's own IANA time zone (e.g.
// "Europe/Lisbon"), so everyone sees the same wall clock wherever they are.
// Every helper that takes `timeZone` falls back to the viewer's zone without it.

const pad = (n: number) => String(n).padStart(2, '0');

type When = Date | string;
const toDate = (value: When) =>
  typeof value === 'string' ? new Date(value) : value;

type Wall = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

const zoneFormats = new Map<string, Intl.DateTimeFormat>();

/** The wall-clock reading of an instant in `timeZone` (or the viewer's zone). */
function wall(date: Date, timeZone?: string): Wall {
  if (!timeZone) {
    return {
      year: date.getFullYear(),
      month: date.getMonth() + 1,
      day: date.getDate(),
      hour: date.getHours(),
      minute: date.getMinutes(),
    };
  }
  let format = zoneFormats.get(timeZone);
  if (!format) {
    format = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
    });
    zoneFormats.set(timeZone, format);
  }
  const parts: Record<string, number> = {};
  for (const part of format.formatToParts(date))
    parts[part.type] = Number(part.value);
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour % 24,
    minute: parts.minute,
  };
}

/** Minutes east of UTC in `timeZone` at that instant ("-300" for New York in winter). */
function offsetMinutes(date: Date, timeZone?: string): number {
  if (!timeZone) return -date.getTimezoneOffset();
  const w = wall(date, timeZone);
  const minute = Math.floor(date.getTime() / 60_000) * 60_000;
  return (
    (Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute) - minute) / 60_000
  );
}

/**
 * Trip dates are plain calendar dates ("2027-03-14"). `new Date(string)` would
 * read them as UTC midnight and show the previous day west of Greenwich, so
 * build a local date instead.
 */
export function parseDateOnly(value: string): Date {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
}

/** The calendar date of a timestamp in `timeZone`, as "YYYY-MM-DD". */
export function localDateKey(value: When, timeZone?: string): string {
  const w = wall(toDate(value), timeZone);
  return `${w.year}-${pad(w.month)}-${pad(w.day)}`;
}

const upper = (s: string) => s.toUpperCase();

/** "MAR 14" */
export function shortDate(date: Date, timeZone?: string): string {
  return upper(
    date
      .toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone })
      .replace(',', ''),
  );
}

/** "MAR 14 → MAR 19" for a trip's date range. */
export function tripDates(start: string, end: string): string {
  return `${shortDate(parseDateOnly(start))} → ${shortDate(parseDateOnly(end))}`;
}

/** "18:30" */
export function clock(value: When, timeZone?: string): string {
  const w = wall(toDate(value), timeZone);
  return `${pad(w.hour)}:${pad(w.minute)}`;
}

/** "SAT" */
export function weekday(date: Date, timeZone?: string): string {
  return upper(
    date.toLocaleDateString('en-US', { weekday: 'short', timeZone }),
  );
}

/** "SAT MAR 15 · 18:30–20:30" (the end date is shown when it differs). */
export function activityWhen(
  startsAt: string,
  endsAt: string,
  timeZone?: string,
): string {
  const start = new Date(startsAt);
  const end = new Date(endsAt);
  const dayOf = (d: Date) =>
    `${weekday(d, timeZone)} ${shortDate(d, timeZone)}`;
  const endPart =
    localDateKey(start, timeZone) === localDateKey(end, timeZone)
      ? clock(end, timeZone)
      : `${dayOf(end)} ${clock(end, timeZone)}`;
  return `${dayOf(start)} · ${clock(start, timeZone)}–${endPart}`;
}

/** "Lisbon time (GMT+1)": which clock a trip's times are on. */
export function zoneLabel(timeZone: string, at: Date = new Date()): string {
  const city = (timeZone.split('/').pop() ?? timeZone).replace(/_/g, ' ');
  const offset = new Intl.DateTimeFormat('en-US', {
    timeZone,
    timeZoneName: 'shortOffset',
  })
    .formatToParts(at)
    .find((part) => part.type === 'timeZoneName')?.value;
  return offset ? `${city} time (${offset})` : `${city} time`;
}

/** The viewer's own IANA zone, e.g. "America/New_York". */
export function viewerTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
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

/** Value for an <input type="datetime-local"> showing `date` in `timeZone`. */
export function toDateTimeLocal(date: Date, timeZone?: string): string {
  return `${localDateKey(date, timeZone)}T${clock(date, timeZone)}`;
}

/**
 * Reads a datetime-local value ("2027-03-15T20:30") as a wall-clock time in
 * `timeZone` and returns it with that zone's UTC offset, for example
 * "2027-03-15T20:30:00-04:00". The backend requires an offset.
 */
export function fromDateTimeLocal(value: string, timeZone?: string): string {
  const [y, mo, d, h, mi] = value.split(/[-T:]/).map(Number);
  const asUtc = Date.UTC(y, mo - 1, d, h, mi);
  // Guess with the offset at that time read as UTC, then correct once: the
  // second pass settles it when a daylight-saving change falls in between.
  let instant = asUtc - offsetMinutes(new Date(asUtc), timeZone) * 60_000;
  instant = asUtc - offsetMinutes(new Date(instant), timeZone) * 60_000;
  const date = new Date(instant);
  const offset = offsetMinutes(date, timeZone);
  const abs = Math.abs(offset);
  const zone = `${offset < 0 ? '-' : '+'}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
  return `${toDateTimeLocal(date, timeZone)}:00${zone}`;
}

/** Milliseconds since epoch for a datetime-local value read in `timeZone`. */
export function instantOf(value: string, timeZone?: string): number {
  return new Date(fromDateTimeLocal(value, timeZone)).getTime();
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
