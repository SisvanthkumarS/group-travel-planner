import { describe, expect, it } from 'vitest';
import type { Invitation } from '../../frontend/src/api/types';
import { describeInvitation } from '../../frontend/src/lib/invitations';

const ids = {
  invitation_id: 9,
  trip_id: 12,
  invited_user_id: 8,
  invited_by_user_id: 7,
  status: 'PENDING',
  created_at: '2026-11-03T15:00:00Z',
  responded_at: null,
} as const;

describe('describeInvitation (US-06)', () => {
  it('names the trip, destination, dates and Organizer', () => {
    const invitation: Invitation = {
      ...ids,
      trip_name: 'Lisbon Weekend',
      destination: 'Lisbon, Portugal',
      start_date: '2026-11-05',
      end_date: '2026-11-08',
      invited_by_user_name: 'Sisvanthkumar',
    };
    expect(describeInvitation(invitation)).toEqual({
      title: 'Lisbon Weekend',
      destination: 'Lisbon, Portugal',
      dates: 'NOV 5 → NOV 8',
      invitedBy: 'Sisvanthkumar',
    });
  });

  it('falls back instead of crashing when an older backend sends only IDs', () => {
    expect(describeInvitation(ids)).toEqual({
      title: 'Trip invitation',
      destination: null,
      dates: null,
      invitedBy: null,
    });
  });

  it('skips the dates unless both are present', () => {
    const summary = describeInvitation({ ...ids, start_date: '2026-11-05' });
    expect(summary.dates).toBeNull();
  });
});
