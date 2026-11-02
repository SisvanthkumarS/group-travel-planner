import { useState } from 'react';
import { useProposals } from '../../api/hooks';
import type { Proposal } from '../../api/types';
import {
  Avatar,
  PlusIcon,
  QueryError,
  StatusChip,
} from '../../components/bits';
import { activityWhen, weekday, shortDate } from '../../lib/format';
import {
  activeProposals,
  historyProposals,
  needsYou,
  resultLine,
  type NeedsYouItem,
} from '../../lib/proposals';
import { useNow, useTripContext } from './context';
import { NewProposalModal } from './NewProposalModal';
import { ProposalCard } from './ProposalCard';

const NEEDS_YOU_COPY: Record<
  NeedsYouItem['kind'],
  { label: (p: Proposal) => string; action: string }
> = {
  tie: {
    label: (p) => `TIE ${p.poll?.yes_count}–${p.poll?.no_count}`,
    action: 'Break the tie',
  },
  vote: { label: () => 'YOUR VOTE', action: 'Vote now' },
  'open-poll': { label: () => 'NO POLL YET', action: 'Open a poll' },
};

function NeedsYou({ items }: { items: NeedsYouItem[] }) {
  if (items.length === 0) return null;
  return (
    <section className="needs-you" aria-labelledby="needs-you-title">
      <div className="needs-you__head">
        <h2 id="needs-you-title" className="needs-you__title">
          Needs you
        </h2>
        <span className="mono needs-you__count">{items.length}</span>
      </div>
      <div className="needs-you__grid">
        {items.map(({ kind, proposal }) => {
          const start = new Date(proposal.starts_at);
          return (
            <a
              key={`${kind}-${proposal.proposal_id}`}
              href={`#proposal-${proposal.proposal_id}`}
              className="needs-you__item"
            >
              <div className="needs-you__text">
                <span
                  className={`mono eyebrow ${kind === 'tie' ? 'eyebrow--warm' : ''}`}
                >
                  {NEEDS_YOU_COPY[kind].label(proposal)} · {weekday(start)}{' '}
                  {shortDate(start)}
                </span>
                <span className="needs-you__name">{proposal.title}</span>
              </div>
              <span className="needs-you__action">
                {NEEDS_YOU_COPY[kind].action}
              </span>
            </a>
          );
        })}
      </div>
    </section>
  );
}

function History({ proposals }: { proposals: Proposal[] }) {
  const { memberName } = useTripContext();
  const [open, setOpen] = useState(true);
  if (proposals.length === 0) return null;

  return (
    <section className="history" aria-labelledby="history-title">
      <div className="section-head">
        <div className="section-head__title">
          <h2 id="history-title" className="section-title">
            History
          </h2>
          <span className="muted">{proposals.length} decided</span>
        </div>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          aria-expanded={open}
          aria-controls="history-list"
          onClick={() => setOpen((o) => !o)}
        >
          {open ? 'Hide history' : 'Show history'}
        </button>
      </div>
      {open && (
        <ul id="history-list" className="history__list">
          {proposals.map((p) => {
            const struck = p.status === 'WITHDRAWN' || p.status === 'CANCELLED';
            return (
              <li key={p.proposal_id} className="history__row">
                <StatusChip status={p.status} />
                <span
                  className={`history__title ${struck ? 'history__title--struck' : ''}`}
                >
                  {p.title}
                </span>
                <span className="mono small muted-strong">
                  {activityWhen(p.starts_at, p.ends_at)}
                </span>
                <span className="mono small history__result">
                  {p.status === 'WITHDRAWN' && !p.poll
                    ? `by ${memberName(p.author_id)}, before voting`
                    : resultLine(p)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Sidebar() {
  const { members, viewer } = useTripContext();
  return (
    <aside className="trip-aside">
      <section className="card">
        <div className="section-head">
          <h2 className="card__title">Travelers</h2>
          <span className="mono small muted">{members.length} / 8</span>
        </div>
        <ul className="member-list">
          {members.map((m) => (
            <li key={m.user_id} className="member-list__row">
              <Avatar name={m.user_name} userId={m.user_id} />
              <span className="member-list__name">
                {m.user_name}
                {m.user_id === viewer.userId && (
                  <span className="muted"> (you)</span>
                )}
              </span>
              {m.role === 'ORGANIZER' && (
                <span className="small strong accent">Organizer</span>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section className="card">
        <h2 className="card__title">How decisions work</h2>
        <ul className="rules">
          <li>
            More Yes than No when the poll closes: added to the itinerary.
          </li>
          <li>More No, or no votes at all: not added.</li>
          <li>An exact tie goes to the organizer.</li>
        </ul>
      </section>
    </aside>
  );
}

/** US-07 to US-14: submit, poll, vote, resolve, withdraw and review proposals. */
export function ProposalsTab() {
  const { trip, viewer } = useTripContext();
  const proposals = useProposals(trip.trip_id);
  const now = useNow(15_000);
  const [proposing, setProposing] = useState(false);

  const list = proposals.data ?? [];
  const active = activeProposals(list);

  return (
    <div className="trip-body">
      <section className="trip-main">
        {proposals.error ? (
          <QueryError
            error={proposals.error}
            onRetry={() => proposals.refetch()}
          />
        ) : proposals.isPending ? (
          <p className="muted" role="status">
            Loading proposals…
          </p>
        ) : (
          <>
            <NeedsYou items={needsYou(list, viewer, now)} />

            <div className="section-head">
              <div className="section-head__title">
                <h2 className="section-title">Active</h2>
                <span className="muted">
                  Voting first, then waiting for a poll
                </span>
              </div>
              <button
                type="button"
                className="btn btn--primary btn--md"
                onClick={() => setProposing(true)}
              >
                <PlusIcon />
                New proposal
              </button>
            </div>

            {active.length === 0 ? (
              <div className="empty">
                <p>
                  Nothing up for a vote. Suggest an activity to get things
                  going.
                </p>
              </div>
            ) : (
              active.map((p) => (
                <ProposalCard key={p.proposal_id} proposal={p} now={now} />
              ))
            )}

            <History proposals={historyProposals(list)} />
          </>
        )}
      </section>
      <Sidebar />
      {proposing && <NewProposalModal onClose={() => setProposing(false)} />}
    </div>
  );
}
