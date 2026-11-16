import { describe, expect, it } from 'vitest';
import type { AppNotification } from '../../frontend/src/api/types';
import {
  flattenPages,
  newestLoadedId,
  notificationKind,
  notificationLink,
  readableMessage,
  timeAgo,
  unreadBadge,
} from '../../frontend/src/lib/notifications';

const note = (over: Partial<AppNotification> = {}): AppNotification => ({
  notification_id: 42,
  event_type: 'POLL_OPENED',
  title: 'Voting is open',
  message: 'Vote on Museum before Friday.',
  trip_name: 'NYC weekend',
  trip_id: 12,
  proposal_id: 9,
  invitation_id: null,
  created_at: '2027-06-30T12:00:00Z',
  read_at: null,
  action_url: '/trips/12',
  ...over,
});

describe('unread badge', () => {
  it('shows nothing at zero or before the count loads', () => {
    expect(unreadBadge(0)).toBeNull();
    expect(unreadBadge(undefined)).toBeNull();
  });

  it('caps at 99+', () => {
    expect(unreadBadge(7)).toBe('7');
    expect(unreadBadge(99)).toBe('99');
    expect(unreadBadge(100)).toBe('99+');
  });
});

describe('notification links', () => {
  it('points a proposal update at that proposal on the trip page', () => {
    expect(notificationLink(note())).toBe('/trips/12#proposal-9');
  });

  it('uses itinerary and invitation links as given', () => {
    expect(
      notificationLink(
        note({
          event_type: 'ACTIVITY_APPROVED',
          action_url: '/trips/12/itinerary',
        }),
      ),
    ).toBe('/trips/12/itinerary');
    expect(
      notificationLink(
        note({
          event_type: 'INVITATION_RECEIVED',
          proposal_id: null,
          invitation_id: 5,
          action_url: '/trips',
        }),
      ),
    ).toBe('/trips');
  });

  it('has no link once the trip is deleted', () => {
    expect(
      notificationLink(
        note({ trip_id: null, proposal_id: null, action_url: null }),
      ),
    ).toBeNull();
  });
});

describe('time labels', () => {
  const now = Date.parse('2027-06-30T12:00:00Z');
  it('counts up from just now to days', () => {
    expect(timeAgo('2027-06-30T11:59:30Z', now)).toBe('Just now');
    expect(timeAgo('2027-06-30T11:55:00Z', now)).toBe('5m ago');
    expect(timeAgo('2027-06-30T09:00:00Z', now)).toBe('3h ago');
    expect(timeAgo('2027-06-28T12:00:00Z', now)).toBe('2d ago');
  });

  it('switches to a date after a week, with the year only if it differs', () => {
    expect(timeAgo('2027-06-01T12:00:00Z', now)).toBe('Jun 1');
    expect(timeAgo('2026-06-01T12:00:00Z', now)).toBe('Jun 1, 2026');
  });
});

describe('message text', () => {
  it('turns raw timestamps into readable times', () => {
    expect(
      readableMessage(
        'Vote on Museum in NYC weekend before 2027-07-01T18:00:00+00:00.',
        'America/New_York',
      ),
    ).toBe('Vote on Museum in NYC weekend before Jul 1, 2:00 PM.');
  });

  it('leaves messages without timestamps alone', () => {
    expect(readableMessage('Ana joined Lisbon spring.')).toBe(
      'Ana joined Lisbon spring.',
    );
  });
});

describe('paging and mark all read', () => {
  const pages = [
    {
      items: [note({ notification_id: 50 }), note({ notification_id: 49 })],
      next_before_id: 49,
    },
    { items: [note({ notification_id: 48 })], next_before_id: null },
  ];

  it('lists every loaded page in order', () => {
    expect(flattenPages(pages).map((n) => n.notification_id)).toEqual([
      50, 49, 48,
    ]);
    expect(flattenPages(undefined)).toEqual([]);
  });

  it('marks through the newest notification on screen', () => {
    expect(newestLoadedId(flattenPages(pages))).toBe(50);
    expect(newestLoadedId([])).toBeUndefined();
  });
});

describe('labels', () => {
  it('names every event type', () => {
    expect(notificationKind('POLL_TIED')).toEqual({
      label: 'Tie',
      tone: 'chip--warm',
    });
    expect(notificationKind('TRIP_DELETED').label).toBe('Trip deleted');
  });
});
