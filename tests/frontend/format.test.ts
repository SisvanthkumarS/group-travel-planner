import { describe, expect, it } from 'vitest';
import {
  activityWhen,
  countdown,
  eachDay,
  fromDateTimeLocal,
  money,
  parseDateOnly,
  toDateTimeLocal,
  tripDates,
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

  it('sends local times with their UTC offset, not as Z', () => {
    const sent = fromDateTimeLocal('2027-03-15T20:30');
    // Same wall-clock date and time the traveler picked...
    expect(sent).toMatch(/^2027-03-15T20:30:00[+-]\d{2}:\d{2}$/);
    // ...and the same instant.
    expect(new Date(sent).getTime()).toBe(
      new Date('2027-03-15T20:30').getTime(),
    );
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
