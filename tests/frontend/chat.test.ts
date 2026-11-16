import { describe, expect, it } from 'vitest';
import { ApiError } from '../../frontend/src/api/client';
import type { ChatDraft, ChatMessage } from '../../frontend/src/api/types';
import {
  aiIsAnswering,
  askAiError,
  askerOf,
  conversation,
  draftDecider,
} from '../../frontend/src/lib/chat';

const msg = (id: number, over: Partial<ChatMessage> = {}): ChatMessage => ({
  message_id: id,
  chat_id: 1,
  role: 'USER',
  content: `message ${id}`,
  status: 'COMPLETED',
  created_at: '2027-03-01T12:00:00Z',
  user_id: 7,
  reply_to_message_id: null,
  draft: null,
  ...over,
});

const draft = (over: Partial<ChatDraft> = {}): ChatDraft => ({
  kind: 'PROPOSAL',
  proposals: [],
  draft_id: 3,
  message_id: 11,
  status: 'PENDING',
  created_at: '2027-03-01T12:00:00Z',
  decided_at: null,
  proposal_ids: [],
  asked_by_user_id: 7,
  ...over,
});

describe('conversation order', () => {
  it('reads oldest first across pages that arrive newest first', () => {
    const pages = [
      { messages: [msg(12), msg(11)], next_before_id: 11 },
      { messages: [msg(10), msg(9)], next_before_id: null },
    ];
    expect(conversation(pages).map((m) => m.message_id)).toEqual([
      9, 10, 11, 12,
    ]);
  });

  it('drops a message that shows up on two pages after new ones arrive', () => {
    const pages = [
      { messages: [msg(13), msg(12)], next_before_id: 12 },
      { messages: [msg(12), msg(11)], next_before_id: null },
    ];
    expect(conversation(pages).map((m) => m.message_id)).toEqual([11, 12, 13]);
  });
});

describe('one AI answer at a time', () => {
  it('finds the reply that is still being written', () => {
    const thinking = msg(5, {
      role: 'ASSISTANT',
      status: 'GENERATING',
      user_id: null,
    });
    expect(aiIsAnswering([msg(4), thinking])).toBe(thinking);
  });

  it('is free once replies are done or failed', () => {
    expect(
      aiIsAnswering([
        msg(4),
        msg(5, { role: 'ASSISTANT', status: 'FAILED', user_id: null }),
      ]),
    ).toBeNull();
  });
});

describe('who decides on a draft', () => {
  it('lets only the member who asked decide', () => {
    expect(draftDecider(draft(), 7)).toBe('you');
    expect(draftDecider(draft(), 8)).toBe('other');
  });

  it('leaves decided drafts and drafts whose asker left alone', () => {
    expect(draftDecider(draft({ status: 'ACCEPTED' }), 7)).toBe('nobody');
    expect(draftDecider(draft({ asked_by_user_id: null }), 7)).toBe('nobody');
  });

  it('names the member an AI reply answers', () => {
    const question = msg(10, { user_id: 8 });
    const reply = msg(11, {
      role: 'ASSISTANT',
      user_id: null,
      reply_to_message_id: 10,
    });
    expect(askerOf(reply, [question, reply])).toBe(8);
    expect(
      askerOf(msg(12, { role: 'ASSISTANT', user_id: null }), []),
    ).toBeNull();
  });
});

describe('Ask AI errors', () => {
  it('keeps the question in the box when it was not saved', () => {
    expect(askAiError(new ApiError(409, 'busy')).questionSaved).toBe(false);
    expect(askAiError(new ApiError(503, 'no provider'))).toEqual({
      message:
        "AI isn't set up on this server yet. Messages to the group still work.",
      questionSaved: false,
    });
  });

  it('shows the server reason when the trip is out of proposal room', () => {
    expect(
      askAiError(new ApiError(409, 'Trip proposal limit reached.')).message,
    ).toBe('Trip proposal limit reached.');
  });

  it('notes the question is already in the chat after a failed answer', () => {
    expect(askAiError(new ApiError(504, 'timeout')).questionSaved).toBe(true);
    expect(askAiError(new ApiError(502, 'bad reply')).questionSaved).toBe(true);
  });
});
