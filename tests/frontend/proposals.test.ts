import { describe, expect, it } from 'vitest';
import type { Poll, Proposal } from '../../frontend/src/api/types';
import {
  activeProposals,
  canVote,
  canWithdraw,
  historyProposals,
  myVote,
  needsYou,
  proposalsRefetchInterval,
  resultLine,
} from '../../frontend/src/lib/proposals';
import { validateProposal } from '../../frontend/src/pages/trip/NewProposalModal';
import { validateTrip } from '../../frontend/src/pages/CreateTripModal';
import { groupByDay } from '../../frontend/src/pages/trip/ItineraryTab';

const NOW = new Date('2027-03-10T12:00:00Z').getTime();
const ME = 1;
const ORGANIZER = { userId: ME, isOrganizer: true };
const MEMBER = { userId: ME, isOrganizer: false };

function poll(overrides: Partial<Poll> = {}): Poll {
  return {
    poll_id: 10,
    proposal_id: 1,
    status: 'OPEN',
    deadline: '2027-03-11T12:00:00Z',
    opened_at: '2027-03-09T12:00:00Z',
    closed_at: null,
    outcome: null,
    yes_count: 0,
    no_count: 0,
    total_votes: 0,
    eligible_voter_ids: [1, 2, 3],
    votes: [],
    voting_history: [],
    resolution: null,
    ...overrides,
  };
}

let nextId = 1;
function proposal(overrides: Partial<Proposal> = {}): Proposal {
  const id = nextId++;
  return {
    proposal_id: id,
    trip_id: 1,
    author_id: 2,
    title: `Proposal ${id}`,
    description: 'd',
    estimated_cost: '10.00',
    location: 'l',
    starts_at: '2027-03-15T18:00:00Z',
    ends_at: '2027-03-15T20:00:00Z',
    status: 'PENDING',
    created_at: '2027-03-01T00:00:00Z',
    poll: null,
    ...overrides,
  };
}

const vote = (user_id: number, choice: 'YES' | 'NO') => ({
  poll_id: 10,
  user_id,
  choice,
  updated_at: '2027-03-10T00:00:00Z',
});

describe('voting rules (US-09)', () => {
  it('lets an eligible user vote before the deadline', () => {
    expect(canVote(proposal({ status: 'OPEN', poll: poll() }), ME, NOW)).toBe(
      true,
    );
  });

  it('blocks users who were not eligible when the poll opened', () => {
    expect(
      canVote(
        proposal({
          status: 'OPEN',
          poll: poll({ eligible_voter_ids: [2, 3] }),
        }),
        ME,
        NOW,
      ),
    ).toBe(false);
  });

  it('blocks voting at or after the deadline', () => {
    const p = proposal({
      status: 'OPEN',
      poll: poll({ deadline: '2027-03-10T12:00:00Z' }),
    });
    expect(canVote(p, ME, NOW)).toBe(false);
  });

  it("finds the current user's vote", () => {
    const p = poll({ votes: [vote(2, 'NO'), vote(1, 'YES')] });
    expect(myVote(p, ME)).toBe('YES');
    expect(myVote(p, 3)).toBeNull();
    expect(myVote(null, ME)).toBeNull();
  });
});

describe('withdraw rules (US-14)', () => {
  it('allows the author while pending or open', () => {
    expect(
      canWithdraw(proposal({ author_id: ME, status: 'PENDING' }), ME),
    ).toBe(true);
    expect(canWithdraw(proposal({ author_id: ME, status: 'OPEN' }), ME)).toBe(
      true,
    );
  });

  it('denies other users and decided proposals', () => {
    expect(canWithdraw(proposal({ author_id: 2, status: 'PENDING' }), ME)).toBe(
      false,
    );
    expect(canWithdraw(proposal({ author_id: ME, status: 'TIED' }), ME)).toBe(
      false,
    );
    expect(
      canWithdraw(proposal({ author_id: ME, status: 'APPROVED' }), ME),
    ).toBe(false);
  });
});

describe('needsYou', () => {
  const tied = proposal({
    status: 'TIED',
    poll: poll({ status: 'CLOSED', outcome: 'TIED' }),
  });
  const unvoted = proposal({ status: 'OPEN', poll: poll() });
  const voted = proposal({
    status: 'OPEN',
    poll: poll({ votes: [vote(ME, 'NO')] }),
  });
  const pending = proposal({ status: 'PENDING' });
  const pendingPast = proposal({
    status: 'PENDING',
    starts_at: '2027-03-01T00:00:00Z',
  });

  it('lists ties first, then missing votes, then polls to open, for the organizer', () => {
    const items = needsYou(
      [pending, voted, unvoted, tied, pendingPast],
      ORGANIZER,
      NOW,
    );
    expect(items.map((i) => [i.kind, i.proposal.proposal_id])).toEqual([
      ['tie', tied.proposal_id],
      ['vote', unvoted.proposal_id],
      ['open-poll', pending.proposal_id],
    ]);
  });

  it('shows members only their missing votes', () => {
    expect(
      needsYou([tied, unvoted, pending], MEMBER, NOW).map((i) => i.kind),
    ).toEqual(['vote']);
  });
});

describe('grouping (US-13)', () => {
  it('orders active proposals: voting by deadline, then ties, then pending by start', () => {
    const lateDeadline = proposal({
      status: 'OPEN',
      poll: poll({ deadline: '2027-03-12T00:00:00Z' }),
    });
    const soonDeadline = proposal({
      status: 'OPEN',
      poll: poll({ deadline: '2027-03-10T18:00:00Z' }),
    });
    const tie = proposal({ status: 'TIED' });
    const pendingLate = proposal({
      status: 'PENDING',
      starts_at: '2027-03-18T00:00:00Z',
    });
    const pendingEarly = proposal({
      status: 'PENDING',
      starts_at: '2027-03-14T00:00:00Z',
    });
    const done = proposal({ status: 'APPROVED' });

    expect(
      activeProposals([
        pendingLate,
        done,
        tie,
        lateDeadline,
        pendingEarly,
        soonDeadline,
      ]),
    ).toEqual([soonDeadline, lateDeadline, tie, pendingEarly, pendingLate]);
  });

  it('puts every decided status in history, including cancelled', () => {
    const statuses = [
      'APPROVED',
      'REJECTED',
      'WITHDRAWN',
      'CANCELLED',
    ] as const;
    const decided = statuses.map((status) => proposal({ status }));
    expect(
      historyProposals([...decided, proposal({ status: 'OPEN' })]),
    ).toHaveLength(4);
  });

  it('describes results, keeping the tie story after resolution', () => {
    expect(
      resultLine(
        proposal({
          status: 'APPROVED',
          poll: poll({ yes_count: 5, no_count: 1 }),
        }),
      ),
    ).toBe('YES 5 · NO 1');
    const resolved = poll({
      outcome: 'TIED',
      yes_count: 2,
      no_count: 2,
      resolution: {
        decision: 'APPROVE',
        resolved_by_user_id: 1,
        resolved_at: '2027-03-10T00:00:00Z',
      },
    });
    expect(resultLine(proposal({ status: 'CANCELLED', poll: resolved }))).toBe(
      'TIE 2–2 · ORGANIZER APPROVED',
    );
  });
});

describe('refetching around poll deadlines (US-10a)', () => {
  it('does not poll when nothing is open', () => {
    expect(proposalsRefetchInterval([proposal()], NOW)).toBe(false);
    expect(proposalsRefetchInterval(undefined, NOW)).toBe(false);
  });

  it('refetches shortly after the next deadline, within bounds', () => {
    const soon = proposal({
      status: 'OPEN',
      poll: poll({ deadline: new Date(NOW + 5_000).toISOString() }),
    });
    expect(proposalsRefetchInterval([soon], NOW)).toBe(12_000);
    const far = proposal({
      status: 'OPEN',
      poll: poll({ deadline: new Date(NOW + 86_400_000).toISOString() }),
    });
    expect(proposalsRefetchInterval([far], NOW)).toBe(20_000);
  });
});

describe('create trip validation (US-04)', () => {
  const ok = {
    name: 'Lisbon',
    destination: 'Lisbon, Portugal',
    start_date: '2027-03-14',
    end_date: '2027-03-19',
    timezone: 'Europe/Lisbon',
  };
  it('accepts a valid trip, including a one-day trip', () => {
    expect(validateTrip(ok)).toEqual({});
    expect(validateTrip({ ...ok, end_date: ok.start_date })).toEqual({});
  });
  it('rejects an end date before the start date', () => {
    expect(validateTrip({ ...ok, end_date: '2027-03-13' }).end_date).toMatch(
      /before/,
    );
  });
  it('requires a time zone', () => {
    expect(validateTrip({ ...ok, timezone: '' }).timezone).toMatch(/time zone/);
  });
});

describe('proposal validation (US-07)', () => {
  const trip = {
    start_date: '2027-03-14',
    end_date: '2027-03-19',
    timezone: 'Europe/Lisbon',
  };
  const ok = {
    title: 'Fado night',
    location: 'Alfama',
    starts_at: '2027-03-15T21:00',
    ends_at: '2027-03-15T23:30',
    estimated_cost: '35',
    description: 'Live music',
  };

  it('accepts a valid proposal', () => {
    expect(validateProposal(ok, trip, NOW)).toEqual({});
  });

  it('rejects negative cost, missing fields and bad times', () => {
    const errors = validateProposal(
      { ...ok, title: ' ', estimated_cost: '-1', ends_at: '2027-03-15T20:00' },
      trip,
      NOW,
    );
    expect(Object.keys(errors).sort()).toEqual([
      'ends_at',
      'estimated_cost',
      'title',
    ]);
  });

  it('rejects times outside the trip dates or in the past', () => {
    expect(
      validateProposal({ ...ok, ends_at: '2027-03-20T01:00' }, trip, NOW)
        .ends_at,
    ).toMatch(/trip dates/);
    expect(
      validateProposal({ ...ok, starts_at: '2027-03-01T10:00' }, trip, NOW)
        .starts_at,
    ).toMatch(/future/);
  });

  it('reads times on the trip clock, so a late evening on the last day fits', () => {
    const ny = { ...trip, timezone: 'America/New_York' };
    // 20:30 in New York on the last day is already the next day in UTC.
    expect(
      validateProposal(
        { ...ok, starts_at: '2027-03-19T20:30', ends_at: '2027-03-19T22:00' },
        ny,
        NOW,
      ),
    ).toEqual({});
  });

  it('judges "in the future" on the trip clock', () => {
    // 10:00 in Tokyo is 01:00 UTC, already past at 02:00 UTC.
    const tokyo = { ...trip, timezone: 'Asia/Tokyo' };
    const now = Date.parse('2027-03-15T02:00:00Z');
    expect(
      validateProposal(
        { ...ok, starts_at: '2027-03-15T10:00', ends_at: '2027-03-15T12:00' },
        tokyo,
        now,
      ).starts_at,
    ).toMatch(/future/);
  });
});

describe('itinerary days (US-15)', () => {
  it('has one entry per trip day, in order, with items on their local day', () => {
    const item = {
      item_id: 1,
      trip_id: 1,
      proposal_id: 1,
      title: 'Fado',
      description: '',
      estimated_cost: '35',
      location: 'Alfama',
      starts_at: '2027-03-15T21:00:00Z',
      ends_at: '2027-03-15T23:00:00Z',
      status: 'ACTIVE' as const,
    };
    const days = groupByDay(
      [item],
      [],
      '2027-03-14',
      '2027-03-16',
      'Europe/Lisbon',
    );
    expect(days.map((d) => d.key)).toEqual([
      '2027-03-14',
      '2027-03-15',
      '2027-03-16',
    ]);
    expect(days[1].items).toEqual([item]);
  });

  it('files a late-evening activity under the trip day, not the UTC day', () => {
    const item = {
      item_id: 2,
      trip_id: 1,
      proposal_id: 2,
      title: 'Late dinner',
      description: '',
      estimated_cost: '60',
      location: 'Midtown',
      starts_at: '2027-03-17T00:30:00Z', // 20:30 on Mar 16 in New York
      ends_at: '2027-03-17T02:00:00Z',
      status: 'ACTIVE' as const,
    };
    const days = groupByDay(
      [item],
      [],
      '2027-03-14',
      '2027-03-16',
      'America/New_York',
    );
    expect(days.map((d) => d.key)).toEqual([
      '2027-03-14',
      '2027-03-15',
      '2027-03-16',
    ]);
    expect(days[2].items).toEqual([item]);
  });
});
