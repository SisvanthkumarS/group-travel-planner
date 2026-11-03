import { describe, expect, it } from 'vitest';
import {
  activityWhen,
  countdown,
  clock,
  eachDay,
  fromDateTimeLocal,
  localDateKey,
  money,
  parseDateOnly,
  toDateTimeLocal,
  tripDates,
  zoneLabel,
} from '../../frontend/src/lib/format';

describe('dates', () => {
  it('reads plain dates as local calendar days, not UTC', () => {
    const d = parseDateOnly('2027-03-14');
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2027, 2, 14]);
  });

  it('formats a trip range like a ticket', () => {
    expect(tripDates('2027-03-14', '2027-03-19')).toBe('MAR 14 → MAR 19');
  });

  it('lists every day of a trip inclusively', () => {
    expect(eachDay('2027-02-27', '2027-03-02')).toEqual([
      '2027-02-27',
      '2027-02-28',
      '2027-03-01',
      '2027-03-02',
    ]);
  });

  it('formats activity times, adding the end day when it differs', () => {
    expect(activityWhen('2027-03-15T18:30', '2027-03-15T20:30')).toBe(
      'MON MAR 15 · 18:30–20:30',
    );
    expect(activityWhen('2027-03-15T22:00', '2027-03-16T01:00')).toBe(
      'MON MAR 15 · 22:00–TUE MAR 16 01:00',
    );
  });

  it('round-trips datetime-local values', () => {
    expect(toDateTimeLocal(new Date(2027, 2, 15, 9, 5))).toBe(
      '2027-03-15T09:05',
    );
  });

  it("sends trip-clock times with that zone's offset", () => {
    expect(fromDateTimeLocal('2026-11-20T20:30', 'America/New_York')).toBe(
      '2026-11-20T20:30:00-05:00',
    );
    expect(fromDateTimeLocal('2027-07-01T09:00', 'America/New_York')).toBe(
      '2027-07-01T09:00:00-04:00',
    );
    expect(fromDateTimeLocal('2027-03-15T20:30', 'Asia/Kolkata')).toBe(
      '2027-03-15T20:30:00+05:30',
    );
    expect(fromDateTimeLocal('2027-03-15T20:30', 'UTC')).toBe(
      '2027-03-15T20:30:00+00:00',
    );
  });

  it('handles the days daylight saving changes', () => {
    // New York springs forward at 02:00 on 2027-03-14; 03:30 is EDT.
    expect(fromDateTimeLocal('2027-03-14T03:30', 'America/New_York')).toBe(
      '2027-03-14T03:30:00-04:00',
    );
    expect(fromDateTimeLocal('2027-03-14T01:30', 'America/New_York')).toBe(
      '2027-03-14T01:30:00-05:00',
    );
    // Lisbon falls back at 02:00 on 2027-10-31; 18:00 is back on WET.
    expect(fromDateTimeLocal('2027-10-31T18:00', 'Europe/Lisbon')).toBe(
      '2027-10-31T18:00:00+00:00',
    );
  });

  it('round-trips through the trip clock', () => {
    const sent = fromDateTimeLocal('2027-03-15T20:30', 'Europe/Berlin');
    expect(toDateTimeLocal(new Date(sent), 'Europe/Berlin')).toBe(
      '2027-03-15T20:30',
    );
  });

  it('shows an instant on the trip clock', () => {
    const lateNy = new Date('2026-11-21T01:30:00Z');
    expect(localDateKey(lateNy, 'America/New_York')).toBe('2026-11-20');
    expect(clock(lateNy, 'America/New_York')).toBe('20:30');
    expect(clock(lateNy, 'Asia/Tokyo')).toBe('10:30');
    expect(
      activityWhen(
        '2026-11-21T01:30:00Z',
        '2026-11-21T03:00:00Z',
        'America/New_York',
      ),
    ).toBe('FRI NOV 20 · 20:30–22:00');
  });

  it('names the trip clock', () => {
    const winter = new Date('2027-01-15T12:00:00Z');
    expect(zoneLabel('America/New_York', winter)).toBe('New York time (GMT-5)');
    expect(zoneLabel('Asia/Kolkata', winter)).toBe('Kolkata time (GMT+5:30)');
  });
});

describe('countdown', () => {
  const now = new Date('2027-03-10T12:00:00Z').getTime();
  const at = (ms: number) => new Date(now + ms).toISOString();
  it('picks the right units', () => {
    expect(countdown(at(28 * 3_600_000), now)).toBe('1d 04h');
    expect(countdown(at(3 * 3_600_000 + 20 * 60_000), now)).toBe('3h 20m');
    expect(countdown(at(12 * 60_000), now)).toBe('12m');
    expect(countdown(at(-1), now)).toBe('closing…');
  });
});

describe('money', () => {
  it('formats decimal strings from the API', () => {
    expect(money('45.00')).toBe('$45');
    expect(money('12.50')).toBe('$12.50');
    expect(money(0)).toBe('$0');
  });
});
