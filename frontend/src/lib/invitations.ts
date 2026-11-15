import type { Invitation } from '../api/types';
import { tripDates } from './format';

export type InvitationSummary = {
  title: string;
  destination: string | null;
  dates: string | null;
  invitedBy: string | null;
};

/**
 * What an invitation card shows (US-06). Every field is treated as optional on
 * purpose: a backend older than the frontend sends only IDs, and a missing
 * field must degrade the card, never crash the trips page.
 */
export function describeInvitation(
  invitation: Partial<Invitation>,
): InvitationSummary {
  return {
    title: invitation.trip_name || 'Trip invitation',
    destination: invitation.destination || null,
    dates:
      invitation.start_date && invitation.end_date
        ? tripDates(invitation.start_date, invitation.end_date)
        : null,
    invitedBy: invitation.invited_by_user_name || null,
  };
}
