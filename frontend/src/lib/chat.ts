import { ApiError } from '../api/client';
import type { ChatDraft, ChatMessage, ChatMessagePage } from '../api/types';

/** While the chat is open, new messages and AI progress show up this fast. */
export const CHAT_POLL_MS = 5_000;

export const CHAT_MAX_LENGTH = 4_000;

/** Pages arrive newest first; the conversation reads oldest first. */
export function conversation(pages: ChatMessagePage[] | undefined) {
  const seen = new Set<number>();
  const messages: ChatMessage[] = [];
  for (const page of pages ?? []) {
    for (const m of page.messages) {
      if (seen.has(m.message_id)) continue;
      seen.add(m.message_id);
      messages.push(m);
    }
  }
  return messages.sort((a, b) => a.message_id - b.message_id);
}

/** The room answers one AI question at a time. */
export function aiIsAnswering(messages: ChatMessage[]): ChatMessage | null {
  return (
    messages.find((m) => m.role === 'ASSISTANT' && m.status === 'GENERATING') ??
    null
  );
}

/** Who can act on a draft, from the signed-in member's point of view. */
export function draftDecider(
  draft: ChatDraft,
  viewerId: number,
): 'you' | 'other' | 'nobody' {
  if (draft.status !== 'PENDING') return 'nobody';
  if (draft.asked_by_user_id === null) return 'nobody';
  return draft.asked_by_user_id === viewerId ? 'you' : 'other';
}

/** The member whose question an AI reply answers. */
export function askerOf(
  reply: ChatMessage,
  messages: ChatMessage[],
): number | null {
  if (reply.reply_to_message_id === null) return null;
  return (
    messages.find((m) => m.message_id === reply.reply_to_message_id)?.user_id ??
    null
  );
}

/** Ask AI failures in plain words. The question is kept unless noted. */
export function askAiError(error: unknown): {
  message: string;
  questionSaved: boolean;
} {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 409:
        return {
          message: /limit/i.test(error.message)
            ? error.message
            : 'AI is still answering another question. Ask again once it replies.',
          questionSaved: false,
        };
      case 503:
        return {
          message:
            "AI isn't set up on this server yet. Messages to the group still work.",
          questionSaved: false,
        };
      case 504:
        return {
          message:
            'AI took too long to answer. Your question is in the chat; try asking again.',
          questionSaved: true,
        };
      case 502:
        return {
          message:
            "AI couldn't come up with a usable answer. Your question is in the chat; try rephrasing it.",
          questionSaved: true,
        };
    }
  }
  return {
    message: error instanceof Error ? error.message : 'Could not ask AI.',
    questionSaved: false,
  };
}

/** "1 activity" / "3 activities" */
export function activityCount(n: number): string {
  return n === 1 ? '1 activity' : `${n} activities`;
}
