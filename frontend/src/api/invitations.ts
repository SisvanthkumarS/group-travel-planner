import { apiRequest } from './client';
import type {
  CreateInvitationRequest,
  Invitation,
  RespondInvitationRequest,
} from './types';

export const inviteToTrip = (tripId: number, body: CreateInvitationRequest) =>
  apiRequest<Invitation>(`/trips/${tripId}/invitations`, {
    method: 'POST',
    body,
  });

/** Invitations the current user has received, newest first. */
export const listInvitations = () => apiRequest<Invitation[]>('/invitations');

export const respondToInvitation = (body: RespondInvitationRequest) =>
  apiRequest<Invitation>('/invitations', { method: 'PATCH', body });
