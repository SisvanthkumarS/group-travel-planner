import { useState, type FormEvent } from 'react';
import { ApiError } from '../../api/client';
import {
  useOpenPoll,
  useResolveTie,
  useVote,
  useWithdrawProposal,
} from '../../api/hooks';
import type { Proposal } from '../../api/types';
import { CheckIcon, StatusChip, VoteBar } from '../../components/bits';
import {
  activityWhen,
  countdown,
  fromDateTimeLocal,
  money,
  toDateTimeLocal,
} from '../../lib/format';
import { canVote, canWithdraw, myVote, tally } from '../../lib/proposals';
import { useTripContext } from './context';

const errorText = (e: unknown, fallback: string) =>
  e instanceof ApiError
    ? (e.fieldErrors.deadline ?? e.message)
    : e instanceof Error
      ? e.message
      : fallback;

function VotePanel({ proposal, now }: { proposal: Proposal; now: number }) {
  const { trip, viewer } = useTripContext();
  const castVote = useVote(trip.trip_id);
  const [error, setError] = useState<string | null>(null);
  const poll = proposal.poll!;
  const t = tally(poll);
  const mine = myVote(poll, viewer.userId);
  const eligible = canVote(proposal, viewer.userId, now);
  const notVoted = t.eligible - t.cast;

  async function choose(choice: 'YES' | 'NO') {
    setError(null);
    try {
      await castVote.mutateAsync({ pollId: poll.poll_id, choice });
    } catch (e) {
      setError(errorText(e, 'Your vote was not saved.'));
    }
  }

  return (
    <div className="proposal__panel">
      <div className="panel-row">
        <span className="panel-label">Closes in</span>
        <span className="mono panel-value panel-value--warm">
          {countdown(poll.deadline, now)}
        </span>
      </div>
      <div className="stack stack--tight">
        <VoteBar yes={t.yes} no={t.no} eligible={t.eligible} />
        <div className="panel-row mono small muted-strong">
          <span>
            YES {t.yes} · NO {t.no}
          </span>
          <span>
            {t.cast} of {t.eligible} voted
          </span>
        </div>
      </div>
      {eligible ? (
        <>
          <div
            className="vote-buttons"
            role="group"
            aria-label={`Your vote on ${proposal.title}`}
          >
            {(['YES', 'NO'] as const).map((choice) => (
              <button
                key={choice}
                type="button"
                aria-pressed={mine === choice}
                className={`btn vote-btn ${mine === choice ? 'vote-btn--on' : ''}`}
                onClick={() => choose(choice)}
                disabled={castVote.isPending || mine === choice}
              >
                {mine === choice && <CheckIcon />}
                {choice === 'YES' ? 'Yes' : 'No'}
              </button>
            ))}
          </div>
          <span className="small muted">
            {mine
              ? `You voted ${mine === 'YES' ? 'Yes' : 'No'}. You can change it until the poll closes.`
              : notVoted === 1
                ? 'You are the last one left to vote.'
                : 'Pick one. You can change it until the poll closes.'}
          </span>
        </>
      ) : (
        <span className="small muted">
          {poll.eligible_voter_ids.includes(viewer.userId)
            ? 'Voting has closed. Results appear in a few seconds.'
            : 'You joined after this poll opened, so you can watch but not vote.'}
        </span>
      )}
      {error && (
        <span className="field__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

function TiePanel({ proposal }: { proposal: Proposal }) {
  const { trip, viewer } = useTripContext();
  const resolve = useResolveTie(trip.trip_id);
  const [error, setError] = useState<string | null>(null);
  const poll = proposal.poll!;

  async function decide(decision: 'APPROVE' | 'REJECT') {
    setError(null);
    try {
      await resolve.mutateAsync({ pollId: poll.poll_id, decision });
    } catch (e) {
      setError(errorText(e, 'Could not record your decision.'));
    }
  }

  return (
    <div className="proposal__panel proposal__panel--warm">
      <div className="panel-row">
        <span className="panel-label panel-label--warm">Poll closed</span>
        <span className="mono panel-value">
          {poll.yes_count}–{poll.no_count}
        </span>
      </div>
      {viewer.isOrganizer ? (
        <>
          <p className="small">
            The group split evenly. As organizer, you make the final call.
          </p>
          <div className="vote-buttons">
            <button
              type="button"
              className="btn btn--ink"
              onClick={() => decide('APPROVE')}
              disabled={resolve.isPending}
            >
              Approve
            </button>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => decide('REJECT')}
              disabled={resolve.isPending}
            >
              Reject
            </button>
          </div>
        </>
      ) : (
        <p className="small">
          The group split evenly. The organizer will make the final call.
        </p>
      )}
      {error && (
        <span className="field__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

/** Default deadline: a day from now, or an hour before the activity if sooner. */
function suggestedDeadline(startsAt: string, now: number): string {
  const start = new Date(startsAt).getTime();
  const dayFromNow = now + 24 * 3_600_000;
  const target = Math.min(dayFromNow, start - 3_600_000);
  return toDateTimeLocal(new Date(Math.max(target, now + 10 * 60_000)));
}

function OpenPollPanel({ proposal, now }: { proposal: Proposal; now: number }) {
  const { trip, viewer } = useTripContext();
  const openPoll = useOpenPoll(trip.trip_id);
  const [deadline, setDeadline] = useState(() =>
    suggestedDeadline(proposal.starts_at, now),
  );
  const [error, setError] = useState<string | null>(null);
  const inputId = `deadline-${proposal.proposal_id}`;
  const started = new Date(proposal.starts_at).getTime() <= now;

  if (!viewer.isOrganizer) {
    return (
      <div className="proposal__panel">
        <span className="panel-label">No poll yet</span>
        <p className="small muted">Waiting for the organizer to open voting.</p>
      </div>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!deadline) return setError('Pick when voting closes.');
    const closes = new Date(deadline).getTime();
    if (closes <= Date.now())
      return setError('The deadline must be in the future.');
    if (closes >= new Date(proposal.starts_at).getTime())
      return setError('The deadline must be before the activity starts.');
    try {
      await openPoll.mutateAsync({
        proposalId: proposal.proposal_id,
        deadline: fromDateTimeLocal(deadline),
      });
    } catch (e) {
      setError(errorText(e, 'Could not open the poll.'));
    }
  }

  return (
    <form className="proposal__panel" onSubmit={handleSubmit} noValidate>
      <span className="panel-label">No poll yet</span>
      {started ? (
        <p className="small muted">
          This activity has already started, so it can't be put to a vote.
        </p>
      ) : (
        <>
          <label htmlFor={inputId} className="field__label">
            Voting closes
          </label>
          <input
            id={inputId}
            type="datetime-local"
            className="field__input field__input--mono field__input--sm"
            value={deadline}
            max={toDateTimeLocal(new Date(proposal.starts_at))}
            onChange={(e) => setDeadline(e.target.value)}
            aria-invalid={error ? true : undefined}
          />
          <span className="small muted">
            Must be before the activity starts.
          </span>
          <button
            type="submit"
            className="btn btn--primary btn--md"
            disabled={openPoll.isPending}
          >
            {openPoll.isPending ? 'Opening…' : 'Open poll'}
          </button>
        </>
      )}
      {error && (
        <span className="field__error" role="alert">
          {error}
        </span>
      )}
    </form>
  );
}

/** One active proposal: details on the left, the voting stub on the right. */
export function ProposalCard({
  proposal,
  now,
}: {
  proposal: Proposal;
  now: number;
}) {
  const { trip, viewer, memberName } = useTripContext();
  const withdraw = useWithdrawProposal(trip.trip_id);
  const [error, setError] = useState<string | null>(null);

  async function handleWithdraw() {
    setError(null);
    try {
      await withdraw.mutateAsync(proposal.proposal_id);
    } catch (e) {
      setError(errorText(e, 'Could not withdraw.'));
    }
  }

  const author = memberName(proposal.author_id);

  return (
    <article
      id={`proposal-${proposal.proposal_id}`}
      className={`proposal ${proposal.status === 'TIED' ? 'proposal--tied' : ''}`}
      aria-labelledby={`proposal-${proposal.proposal_id}-title`}
    >
      <div className="proposal__info">
        <div className="proposal__top">
          <StatusChip status={proposal.status} />
          <span className="small muted">Proposed by {author}</span>
        </div>
        <h3
          id={`proposal-${proposal.proposal_id}-title`}
          className="proposal__title"
        >
          {proposal.title}
        </h3>
        <div className="proposal__meta">
          <span className="mono ink">
            {activityWhen(proposal.starts_at, proposal.ends_at)}
          </span>
          <span>{proposal.location}</span>
          <span>Est. {money(proposal.estimated_cost)}</span>
        </div>
        <p className="proposal__desc">{proposal.description}</p>
        {canWithdraw(proposal, viewer.userId) && (
          <button
            type="button"
            className="btn btn--secondary btn--sm proposal__withdraw"
            onClick={handleWithdraw}
            disabled={withdraw.isPending}
          >
            {withdraw.isPending ? 'Withdrawing…' : 'Withdraw'}
          </button>
        )}
        {error && (
          <span className="field__error" role="alert">
            {error}
          </span>
        )}
      </div>
      {proposal.status === 'OPEN' && proposal.poll && (
        <VotePanel proposal={proposal} now={now} />
      )}
      {proposal.status === 'TIED' && proposal.poll && (
        <TiePanel proposal={proposal} />
      )}
      {proposal.status === 'PENDING' && (
        <OpenPollPanel proposal={proposal} now={now} />
      )}
    </article>
  );
}
