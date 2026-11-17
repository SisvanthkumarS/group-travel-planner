import { apiRequest } from './client';
import type {
  ChatContext,
  ChatDraft,
  ChatMessage,
  ChatMessagePage,
  ChatReply,
  DraftDecision,
} from './types';

export const CHAT_PAGE_SIZE = 30;

/** Newest first; pass next_before_id to read further back. */
export function listChatMessages(tripId: number, beforeId?: number) {
  const params = new URLSearchParams({ limit: String(CHAT_PAGE_SIZE) });
  if (beforeId !== undefined) params.set('before_id', String(beforeId));
  return apiRequest<ChatMessagePage>(
    `/trips/${tripId}/chat/messages?${params}`,
  );
}

/** A message to the group. Never calls AI. */
export const sendChatMessage = (tripId: number, content: string) =>
  apiRequest<ChatMessage>(`/trips/${tripId}/chat/messages`, {
    method: 'POST',
    body: { content },
  });

/** Saves the question, then waits for the AI reply (can take a while). */
export const askAi = (tripId: number, content: string) =>
  apiRequest<ChatReply>(`/trips/${tripId}/chat/ask-ai`, {
    method: 'POST',
    body: { content },
  });

/** What AI is told about the trip: details plus the active itinerary. */
export const getChatContext = (tripId: number) =>
  apiRequest<ChatContext>(`/trips/${tripId}/chat/context`);

/** Only the member who asked can decide; the server checks again. */
export const decideDraft = (
  tripId: number,
  draftId: number,
  decision: DraftDecision,
) =>
  apiRequest<ChatDraft>(`/trips/${tripId}/chat/drafts/${draftId}`, {
    method: 'PATCH',
    body: { decision },
  });
