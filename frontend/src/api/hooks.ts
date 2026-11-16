// TanStack Query hooks: one place for cache keys and invalidation rules.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { proposalsRefetchInterval } from '../lib/proposals';
import {
  listInvitations,
  inviteToTrip,
  respondToInvitation,
} from './invitations';
import { cancelItineraryItem, getItinerary } from './itinerary';
import {
  createProposal,
  listProposals,
  openPoll,
  resolvePoll,
  vote,
  withdrawProposal,
} from './proposals';
import { useInfiniteQuery as useChatPages } from '@tanstack/react-query';
import { CHAT_POLL_MS } from '../lib/chat';
import {
  askAi,
  decideDraft,
  getChatContext,
  listChatMessages,
  sendChatMessage,
} from './chat';
import { queryKeys } from './queryClient';
import { createTrip, deleteTrip, getTrip, listTrips } from './trips';
import type {
  CreateInvitationRequest,
  CreateProposalRequest,
  CreateTripRequest,
  RespondInvitationRequest,
  Trip,
} from './types';

// Reads

export const useTrips = () =>
  useQuery({ queryKey: queryKeys.trips, queryFn: listTrips });

export const useTrip = (tripId: number) =>
  useQuery({
    queryKey: queryKeys.trip(tripId),
    queryFn: () => getTrip(tripId),
  });

export const useProposals = (tripId: number) =>
  useQuery({
    queryKey: queryKeys.proposals(tripId),
    queryFn: () => listProposals(tripId),
    refetchInterval: (query) => proposalsRefetchInterval(query.state.data),
  });

export const useItinerary = (tripId: number) =>
  useQuery({
    queryKey: queryKeys.itinerary(tripId),
    queryFn: () => getItinerary(tripId),
  });

export const useInvitations = () =>
  useQuery({ queryKey: queryKeys.invitations, queryFn: listInvitations });

// Shared trip chat. Polls while the chat tab is mounted (and the browser tab
// is visible), so other members' messages and AI progress show up on their own.

export const useChatMessages = (tripId: number) =>
  useChatPages({
    queryKey: queryKeys.chat(tripId),
    queryFn: ({ pageParam }) => listChatMessages(tripId, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (page) => page.next_before_id ?? undefined,
    refetchInterval: CHAT_POLL_MS,
  });

export const useChatContext = (tripId: number) =>
  useQuery({
    queryKey: queryKeys.chatContext(tripId),
    queryFn: () => getChatContext(tripId),
  });

export function useSendChatMessage(tripId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => sendChatMessage(tripId, content),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.chat(tripId) }),
  });
}

/** Refreshes on failure too: a failed answer still leaves the question and a FAILED reply. */
export function useAskAi(tripId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => askAi(tripId, content),
    onSettled: () => qc.invalidateQueries({ queryKey: queryKeys.chat(tripId) }),
  });
}

/** Accepting adds proposals, so the whole trip (chat, proposals) refreshes. */
export function useDecideDraft(tripId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { draftId: number; decision: 'ACCEPT' | 'REJECT' }) =>
      decideDraft(tripId, vars.draftId, vars.decision),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.trip(tripId) }),
  });
}

// Writes

export function useCreateTrip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateTripRequest) => createTrip(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.trips }),
  });
}

export function useDeleteTrip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tripId: number) => deleteTrip(tripId),
    // Drop the trip from the list right away. Its own cached detail is left to
    // expire: removing it while the trip page is still mounted would make that
    // page refetch a trip that no longer exists.
    onSuccess: (_data, tripId) => {
      qc.setQueryData<Trip[]>(queryKeys.trips, (trips) =>
        trips?.filter((t) => t.trip_id !== tripId),
      );
      return qc.invalidateQueries({ queryKey: queryKeys.trips, exact: true });
    },
  });
}

export function useRespondToInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RespondInvitationRequest) => respondToInvitation(body),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.invitations }),
        qc.invalidateQueries({ queryKey: queryKeys.trips }),
      ]),
  });
}

export function useInvite(tripId: number) {
  return useMutation({
    mutationFn: (body: CreateInvitationRequest) => inviteToTrip(tripId, body),
  });
}

/** Anything that changes a proposal refreshes the whole trip (list, itinerary). */
function useTripMutation<TVars>(
  tripId: number,
  fn: (vars: TVars) => Promise<unknown>,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.trip(tripId) }),
  });
}

export const useCreateProposal = (tripId: number) =>
  useTripMutation(tripId, (body: CreateProposalRequest) =>
    createProposal(tripId, body),
  );

export const useWithdrawProposal = (tripId: number) =>
  useTripMutation(tripId, (proposalId: number) => withdrawProposal(proposalId));

export const useOpenPoll = (tripId: number) =>
  useTripMutation(tripId, (vars: { proposalId: number; deadline: string }) =>
    openPoll(vars.proposalId, { deadline: vars.deadline }),
  );

export const useVote = (tripId: number) =>
  useTripMutation(tripId, (vars: { pollId: number; choice: 'YES' | 'NO' }) =>
    vote(vars.pollId, { choice: vars.choice }),
  );

export const useResolveTie = (tripId: number) =>
  useTripMutation(
    tripId,
    (vars: { pollId: number; decision: 'APPROVE' | 'REJECT' }) =>
      resolvePoll(vars.pollId, { decision: vars.decision }),
  );

export const useCancelActivity = (tripId: number) =>
  useTripMutation(tripId, (itemId: number) =>
    cancelItineraryItem(tripId, itemId),
  );
