import { apiRequest } from './client';
import type {
  CreateProposalRequest,
  OpenPollRequest,
  Poll,
  Proposal,
  ResolvePollRequest,
  Vote,
  VoteRequest,
} from './types';

// Proposals

export const listProposals = (tripId: number) =>
  apiRequest<Proposal[]>(`/trips/${tripId}/proposals`);

export const createProposal = (tripId: number, body: CreateProposalRequest) =>
  apiRequest<Proposal>(`/trips/${tripId}/proposals`, { method: 'POST', body });

export const withdrawProposal = (proposalId: number) =>
  apiRequest<Proposal>(`/proposals/${proposalId}/withdraw`, {
    method: 'POST',
  });

// Polls

export const openPoll = (proposalId: number, body: OpenPollRequest) =>
  apiRequest<Poll>(`/proposals/${proposalId}/poll`, { method: 'POST', body });

/** Cast or change the current user's vote. */
export const vote = (pollId: number, body: VoteRequest) =>
  apiRequest<Vote>(`/polls/${pollId}/vote`, { method: 'PUT', body });

/** Organizer decision on a TIED poll. */
export const resolvePoll = (pollId: number, body: ResolvePollRequest) =>
  apiRequest<Proposal>(`/polls/${pollId}/resolve`, { method: 'POST', body });
