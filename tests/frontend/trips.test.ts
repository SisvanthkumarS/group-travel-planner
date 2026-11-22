import { describe, expect, it } from 'vitest';
import {
  movesTripCalendar,
  tripChanges,
  tripFormValues,
} from '../../frontend/src/lib/trips';

const TRIP = {
  name: 'Lisbon spring',
  destination: 'Lisbon',
  start_date: '2027-04-01',
  end_date: '2027-04-05',
  timezone: 'Europe/Lisbon',
};

describe('editing a trip (US-18)', () => {
  it('starts the form from the current trip', () => {
    expect(
      tripFormValues({ ...TRIP, trip_id: 3, organizer_id: 1 } as never),
    ).toEqual(TRIP);
  });

  it('sends nothing when nothing changed', () => {
    expect(tripChanges(TRIP, { ...TRIP })).toEqual({});
  });

  it('ignores edits that only add surrounding spaces', () => {
    expect(tripChanges(TRIP, { ...TRIP, name: '  Lisbon spring ' })).toEqual(
      {},
    );
  });

  it('sends only the changed fields, trimmed', () => {
    expect(
      tripChanges(TRIP, {
        ...TRIP,
        destination: ' Porto ',
        end_date: '2027-04-07',
      }),
    ).toEqual({ destination: 'Porto', end_date: '2027-04-07' });
  });

  it('flags changes to dates or time zone, not to name or destination', () => {
    expect(movesTripCalendar({ name: 'New name' })).toBe(false);
    expect(movesTripCalendar({ destination: 'Porto' })).toBe(false);
    expect(movesTripCalendar({ start_date: '2027-04-02' })).toBe(true);
    expect(movesTripCalendar({ timezone: 'UTC' })).toBe(true);
  });
});
