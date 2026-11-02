// Pure rules for showing proposals. The backend decides outcomes; this only
// sorts, groups and works out what the current user can do.
import type { Poll, Proposal, ProposalStatus } from '../api/types';

export type Viewer = { userId: number; isOrganizer: boolean };

export type Tally = { yes: number; no: number; cast: number; eligible: number };

export function tally(poll: Poll): Tally {
  return {
    yes: poll.yes_count,
    no: poll.no_count,
    cast: poll.total_votes,
    eligible: poll.eligible_voter_ids.length,
  };
}

export function myVote(
  poll: Poll | null | undefined,
  userId: number,
): 'YES' | 'NO' | null {
  return poll?.votes.find((v) => v.user_id === userId)?.choice ?? null;
}

export function canVote(
  proposal: Proposal,
  userId: number,
  now: number = Date.now(),
): boolean {
  const poll = proposal.poll;
  return (
    proposal.status === 'OPEN' &&
    !!poll &&
    poll.status === 'OPEN' &&
    new Date(poll.deadline).getTime() > now &&
    poll.eligible_voter_ids.includes(userId)
  );
}

/** Authors can withdraw only before an outcome (US-14). */
export function canWithdraw(proposal: Proposal, userId: number): boolean {
  return (
    proposal.author_id === userId &&
    (proposal.status === 'PENDING' || proposal.status === 'OPEN')
  );
}

export type NeedsYouItem =
  | { kind: 'tie'; proposal: Proposal }
  | { kind: 'open-poll'; proposal: Proposal }
  | { kind: 'vote'; proposal: Proposal };

/** Things waiting on this user, most urgent first. */
export function needsYou(
  proposals: Proposal[],
  viewer: Viewer,
  now: number = Date.now(),
): NeedsYouItem[] {
  const items: NeedsYouItem[] = [];
  for (const p of proposals) {
    if (viewer.isOrganizer && p.status === 'TIED')
      items.push({ kind: 'tie', proposal: p });
  }
  for (const p of proposals) {
    if (
      canVote(p, viewer.userId, now) &&
      myVote(p.poll, viewer.userId) === null
    ) {
      items.push({ kind: 'vote', proposal: p });
    }
  }
  for (const p of proposals) {
    if (
      viewer.isOrganizer &&
      p.status === 'PENDING' &&
      new Date(p.starts_at).getTime() > now
    ) {
      items.push({ kind: 'open-poll', proposal: p });
    }
  }
  return items;
}

const ACTIVE: ProposalStatus[] = ['OPEN', 'TIED', 'PENDING'];
const ACTIVE_RANK: Record<string, number> = { OPEN: 0, TIED: 1, PENDING: 2 };

const byStart = (a: Proposal, b: Proposal) =>
  new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime();

/** Active: voting first (closing soonest first), then ties, then pending. */
export function activeProposals(proposals: Proposal[]): Proposal[] {
  return proposals
    .filter((p) => ACTIVE.includes(p.status))
    .sort((a, b) => {
      const rank = ACTIVE_RANK[a.status] - ACTIVE_RANK[b.status];
      if (rank !== 0) return rank;
      if (a.status === 'OPEN' && a.poll && b.poll) {
        return (
          new Date(a.poll.deadline).getTime() -
          new Date(b.poll.deadline).getTime()
        );
      }
      return byStart(a, b);
    });
}

/** History: everything decided, in trip order. */
export function historyProposals(proposals: Proposal[]): Proposal[] {
  return proposals.filter((p) => !ACTIVE.includes(p.status)).sort(byStart);
}

export const STATUS_LABEL: Record<ProposalStatus, string> = {
  PENDING: 'Pending',
  OPEN: 'Voting open',
  TIED: 'Tied',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  WITHDRAWN: 'Withdrawn',
  CANCELLED: 'Cancelled',
};

/** "YES 5 · NO 1", or how a tie was settled. */
export function resultLine(proposal: Proposal): string {
  const poll = proposal.poll;
  if (!poll)
    return proposal.status === 'WITHDRAWN' ? 'Withdrawn before voting' : '';
  if (proposal.status === 'WITHDRAWN') return 'Withdrawn while voting';
  const counts = `YES ${poll.yes_count} · NO ${poll.no_count}`;
  if (poll.outcome === 'TIED' && poll.resolution) {
    return `TIE ${poll.yes_count}–${poll.no_count} · ORGANIZER ${poll.resolution.decision === 'APPROVE' ? 'APPROVED' : 'REJECTED'}`;
  }
  return counts;
}

/**
 * How often to refetch proposals: quickly while any poll is open, and right
 * after the next deadline so closed results appear without a reload. The
 * backend closes polls on a ~5 s scheduler, so wait a few seconds past it.
 */
export function proposalsRefetchInterval(
  proposals: Proposal[] | undefined,
  now: number = Date.now(),
): number | false {
  const deadlines = (proposals ?? [])
    .filter((p) => p.status === 'OPEN' && p.poll?.status === 'OPEN')
    .map((p) => new Date(p.poll!.deadline).getTime());
  if (deadlines.length === 0) return false;
  const next = Math.min(...deadlines) - now + 7_000;
  return Math.max(3_000, Math.min(next, 20_000));
}
