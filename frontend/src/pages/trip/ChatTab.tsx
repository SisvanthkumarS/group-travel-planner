import {
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react';
import { Link } from 'react-router-dom';
import {
  useAskAi,
  useChatContext,
  useChatMessages,
  useDecideDraft,
  useSendChatMessage,
} from '../../api/hooks';
import type { ChatDraft, ChatMessage, DraftDecision } from '../../api/types';
import { Avatar, QueryError } from '../../components/bits';
import {
  activityWhen,
  clock,
  localDateKey,
  money,
  shortDate,
  tripDates,
  weekday,
  zoneLabel,
} from '../../lib/format';
import {
  activityCount,
  aiIsAnswering,
  askAiError,
  askerOf,
  CHAT_MAX_LENGTH,
  conversation,
  draftDecider,
} from '../../lib/chat';
import { useTripContext } from './context';

const errorText = (e: unknown, fallback: string) =>
  e instanceof Error ? e.message : fallback;

/** memberName gives "you" and "a former member" for sentences; capitalize those as labels. */
const asLabel = (name: string) =>
  name === 'you' || name === 'a former member'
    ? name.charAt(0).toUpperCase() + name.slice(1)
    : name;

function SparkIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z" />
      <path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" />
    </svg>
  );
}

/** "TODAY", "YESTERDAY" or "SAT MAR 15", in the viewer's own time. */
function dayLabel(iso: string): string {
  const key = localDateKey(iso);
  const today = new Date();
  if (key === localDateKey(today)) return 'TODAY';
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (key === localDateKey(yesterday)) return 'YESTERDAY';
  const date = new Date(iso);
  return `${weekday(date)} ${shortDate(date)}`;
}

/** An AI suggestion. Only the member who asked can add it or dismiss it. */
function DraftCard({
  draft,
  askerName,
}: {
  draft: ChatDraft;
  askerName: string;
}) {
  const { trip, viewer } = useTripContext();
  const decide = useDecideDraft(trip.trip_id);
  const who = draftDecider(draft, viewer.userId);
  const n = draft.proposals.length;

  function choose(decision: DraftDecision) {
    decide.mutate({ draftId: draft.draft_id, decision });
  }

  return (
    <div className={`draft draft--${draft.status.toLowerCase()}`}>
      <div className="draft__head">
        <span className="eyebrow">
          {draft.kind === 'ITINERARY' ? 'SUGGESTED PLAN' : 'SUGGESTED ACTIVITY'}
          {n > 1 && ` · ${activityCount(n).toUpperCase()}`}
        </span>
      </div>
      <ol className="draft__list">
        {draft.proposals.map((p, i) => (
          <li key={i} className="draft__item">
            <span className="draft__title">{p.title}</span>
            <span className="mono draft__when">
              {activityWhen(p.starts_at, p.ends_at, trip.timezone)}
            </span>
            <span className="draft__meta">
              {p.location} · {money(p.estimated_cost)}
            </span>
            {p.description && (
              <span className="draft__desc">{p.description}</span>
            )}
          </li>
        ))}
      </ol>

      {draft.status === 'ACCEPTED' ? (
        <p className="draft__foot ok">
          Added as {n === 1 ? 'a proposal' : `${n} proposals`}.{' '}
          <Link to={`/trips/${trip.trip_id}`}>See proposals</Link>
        </p>
      ) : draft.status === 'REJECTED' ? (
        <p className="draft__foot muted">
          {askerName === 'You' ? 'You' : askerName} dismissed this suggestion.
        </p>
      ) : who === 'you' ? (
        <div className="draft__foot">
          <span className="small muted">
            {n === 1 ? 'It goes' : 'They go'} to Proposals for the group to vote
            on.
          </span>
          <div className="draft__actions">
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => choose('REJECT')}
              disabled={decide.isPending}
            >
              Dismiss
            </button>
            <button
              type="button"
              className="btn btn--ink btn--sm"
              onClick={() => choose('ACCEPT')}
              disabled={decide.isPending}
            >
              {decide.isPending
                ? 'Saving…'
                : n === 1
                  ? 'Add as proposal'
                  : `Add ${n} proposals`}
            </button>
          </div>
        </div>
      ) : (
        <p className="draft__foot small muted">
          {who === 'other'
            ? `Waiting for ${askerName} to add or dismiss it.`
            : 'The member who asked has left, so no one can add this.'}
        </p>
      )}
      {decide.error && (
        <div className="form-error" role="alert">
          {errorText(decide.error, 'Could not save your choice.')}
        </div>
      )}
    </div>
  );
}

function Bubble({
  message,
  messages,
  askedAi,
}: {
  message: ChatMessage;
  messages: ChatMessage[];
  askedAi: boolean;
}) {
  const { viewer, memberName } = useTripContext();
  const nameOf = (id: number | null) =>
    id === null ? 'A former member' : asLabel(memberName(id));
  const ai = message.role === 'ASSISTANT';
  const mine = !ai && message.user_id === viewer.userId;
  const asker = ai ? askerOf(message, messages) : null;

  return (
    <li
      className={`msg${mine ? ' msg--mine' : ''}${ai ? ' msg--ai' : ''}`}
      data-status={message.status}
    >
      {!mine &&
        (ai ? (
          <span className="msg__avatar msg__avatar--ai" aria-hidden="true">
            <SparkIcon />
          </span>
        ) : (
          <span className="msg__avatar">
            <Avatar
              name={nameOf(message.user_id)}
              userId={message.user_id ?? 0}
              size={32}
            />
          </span>
        ))}
      <div className="msg__body">
        <span className="msg__who">
          <strong>{ai ? 'Trip AI' : nameOf(message.user_id)}</strong>
          {ai && asker !== null && <> · answering {memberName(asker)}</>}
          {askedAi && <span className="chip chip--blue">Asked AI</span>}
          <time className="mono" dateTime={message.created_at}>
            {clock(message.created_at)}
          </time>
        </span>
        {message.status === 'GENERATING' ? (
          <span className="msg__text msg__text--thinking" role="status">
            Thinking
            <span className="dots" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
          </span>
        ) : message.status === 'FAILED' ? (
          <span className="msg__text msg__text--failed">
            Couldn't answer this one. Ask again to retry.
          </span>
        ) : message.status === 'CANCELLED' ? (
          <span className="msg__text msg__text--failed">
            This answer was cancelled.
          </span>
        ) : (
          <span className="msg__text">{message.content}</span>
        )}
        {message.draft && (
          <DraftCard draft={message.draft} askerName={nameOf(asker)} />
        )}
      </div>
    </li>
  );
}

function Composer({
  answering,
  onPosting,
  onAsked,
}: {
  answering: ChatMessage | null;
  onPosting: () => void;
  onAsked: () => void;
}) {
  const { trip } = useTripContext();
  const send = useSendChatMessage(trip.trip_id);
  const ask = useAskAi(trip.trip_id);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const content = text.trim();
  const tooLong = content.length > CHAT_MAX_LENGTH;

  async function sendToGroup() {
    if (!content || tooLong || send.isPending) return;
    setError(null);
    onPosting();
    try {
      await send.mutateAsync(content);
      setText('');
    } catch (e) {
      setError(errorText(e, 'Could not send your message.'));
    }
  }

  async function askQuestion() {
    if (!content || tooLong || ask.isPending || answering) return;
    setError(null);
    onPosting();
    setText('');
    // The server saves the question before calling AI; show it right away.
    const early = window.setTimeout(onAsked, 600);
    try {
      await ask.mutateAsync(content);
    } catch (e) {
      const { message, questionSaved } = askAiError(e);
      if (!questionSaved) setText((t) => t || content);
      setError(message);
    } finally {
      window.clearTimeout(early);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendToGroup();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void sendToGroup();
    }
  }

  const askBlocked = Boolean(answering) || ask.isPending;

  return (
    <form className="composer" onSubmit={handleSubmit}>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      <textarea
        id="chat-input"
        aria-label="Message"
        className="composer__input"
        rows={2}
        placeholder="Message the group, or ask AI for ideas…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-invalid={tooLong || undefined}
        aria-describedby="chat-input-hint"
      />
      <div className="composer__bar">
        <span id="chat-input-hint" className="small muted">
          {tooLong
            ? `Keep it under ${CHAT_MAX_LENGTH.toLocaleString()} characters.`
            : ask.isPending
              ? 'AI is working on your question. You can keep chatting.'
              : answering
                ? 'AI is answering a question. You can ask once it replies.'
                : 'Enter sends to the group · Shift+Enter for a new line'}
        </span>
        <div className="composer__actions">
          <button
            type="button"
            className="btn btn--secondary btn--sm composer__ask"
            onClick={() => void askQuestion()}
            disabled={!content || tooLong || askBlocked}
          >
            <SparkIcon />
            {ask.isPending ? 'Asking…' : 'Ask AI'}
          </button>
          <button
            type="submit"
            className="btn btn--primary btn--sm"
            disabled={!content || tooLong || send.isPending}
          >
            {send.isPending ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </form>
  );
}

/** What Ask AI is told: the trip, its active itinerary and recent messages. */
function AiContextCard() {
  const { trip } = useTripContext();
  const context = useChatContext(trip.trip_id);
  return (
    <section className="card" aria-labelledby="ai-context-title">
      <h2 id="ai-context-title" className="card__title">
        What AI knows
      </h2>
      {context.error && context.data === undefined ? (
        <QueryError error={context.error} onRetry={() => context.refetch()} />
      ) : !context.data ? (
        <p className="small muted" role="status">
          Loading…
        </p>
      ) : (
        <>
          <p className="small muted-strong">
            <strong className="ink">{context.data.name}</strong> in{' '}
            {context.data.destination},{' '}
            <span className="mono">
              {tripDates(context.data.start_date, context.data.end_date)}
            </span>
            , {zoneLabel(context.data.timezone)}.
          </p>
          {context.data.itinerary.length === 0 ? (
            <p className="small muted">Nothing on the itinerary yet.</p>
          ) : (
            <ul className="ai-context__list">
              {context.data.itinerary.map((a, i) => (
                <li key={i}>
                  <span className="small strong">{a.title}</span>
                  <span className="mono small muted">
                    {activityWhen(
                      a.starts_at,
                      a.ends_at,
                      context.data.timezone,
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="small muted">
            Plus up to 20 earlier messages from this chat. Everyone sees the
            question and the answer.
          </p>
        </>
      )}
    </section>
  );
}

/** Shared trip chat: group messages, Ask AI, and AI suggestions as drafts. */
export function ChatTab() {
  const { trip } = useTripContext();
  const chat = useChatMessages(trip.trip_id);
  const messages = conversation(chat.data?.pages);
  const answering = aiIsAnswering(messages);
  const askedIds = new Set(
    messages
      .filter((m) => m.role === 'ASSISTANT' && m.reply_to_message_id !== null)
      .map((m) => m.reply_to_message_id),
  );

  // Keep the newest message in view, unless the reader has scrolled up.
  // Loading older messages keeps the reader's place.
  const logRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const shape = useRef({ first: 0, last: 0, height: 0 });
  const first = messages[0]?.message_id ?? 0;
  const last = messages.at(-1)?.message_id ?? 0;
  useLayoutEffect(() => {
    const el = logRef.current;
    if (!el) return;
    const prev = shape.current;
    if (prev.last && first !== prev.first && last === prev.last) {
      el.scrollTop += el.scrollHeight - prev.height;
    } else if (last !== prev.last && nearBottom.current) {
      el.scrollTop = el.scrollHeight;
    }
    shape.current = { first, last, height: el.scrollHeight };
  });

  function scrollToEnd() {
    nearBottom.current = true;
  }

  const days = messages.map((m) => dayLabel(m.created_at));

  return (
    <div className="trip-body">
      <section className="trip-main chat" aria-label="Trip chat">
        <div
          ref={logRef}
          className="chat__log"
          onScroll={(e) => {
            const el = e.currentTarget;
            nearBottom.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          {chat.error && !chat.data ? (
            <QueryError error={chat.error} onRetry={() => chat.refetch()} />
          ) : chat.isPending ? (
            <p className="muted chat__note" role="status">
              Loading chat…
            </p>
          ) : messages.length === 0 ? (
            <p className="chat__empty">
              No messages yet. Say hi to the group, or ask AI for ideas in{' '}
              {trip.destination}.
            </p>
          ) : (
            <>
              {chat.hasNextPage && (
                <button
                  type="button"
                  className="link-btn chat__older"
                  onClick={() => chat.fetchNextPage()}
                  disabled={chat.isFetchingNextPage}
                >
                  {chat.isFetchingNextPage
                    ? 'Loading…'
                    : 'Load earlier messages'}
                </button>
              )}
              <ol className="chat__list" aria-label="Messages">
                {messages.map((m, i) => (
                  <ChatRow
                    key={m.message_id}
                    divider={days[i] !== days[i - 1] ? days[i] : null}
                    message={m}
                    messages={messages}
                    askedAi={askedIds.has(m.message_id)}
                  />
                ))}
              </ol>
            </>
          )}
        </div>
        <Composer
          answering={answering}
          onPosting={scrollToEnd}
          onAsked={() => void chat.refetch()}
        />
      </section>
      <aside className="trip-aside">
        <AiContextCard />
      </aside>
    </div>
  );
}

function ChatRow({
  divider,
  ...props
}: {
  divider: string | null;
  message: ChatMessage;
  messages: ChatMessage[];
  askedAi: boolean;
}) {
  return (
    <>
      {divider && (
        <li className="chat__day mono" aria-hidden="true">
          {divider}
        </li>
      )}
      <Bubble {...props} />
    </>
  );
}
