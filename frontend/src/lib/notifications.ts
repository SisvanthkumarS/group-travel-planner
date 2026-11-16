import type {
  AppNotification,
  NotificationEventType,
  NotificationPage,
} from '../api/types';

/** Unread badge and the visible first page refresh this often. */
export const NOTIFICATIONS_POLL_MS = 20_000;

/** Header badge text: nothing at zero, "99+" past 99. */
export function unreadBadge(count: number | undefined): string | null {
  if (!count || count <= 0) return null;
  return count > 99 ? '99+' : String(count);
}

type Kind = { label: string; tone: string };

const KINDS: Record<NotificationEventType, Kind> = {
  INVITATION_RECEIVED: { label: 'Invitation', tone: 'chip--blue' },
  INVITATION_ACCEPTED: { label: 'Joined', tone: 'chip--ok' },
  INVITATION_DECLINED: { label: 'Declined', tone: 'chip--grey' },
  PROPOSAL_CREATED: { label: 'New proposal', tone: 'chip--muted' },
  POLL_OPENED: { label: 'Voting open', tone: 'chip--blue' },
  POLL_TIED: { label: 'Tie', tone: 'chip--warm' },
  ACTIVITY_APPROVED: { label: 'Approved', tone: 'chip--ok' },
  ACTIVITY_REJECTED: { label: 'Not added', tone: 'chip--grey' },
  ACTIVITY_CANCELLED: { label: 'Cancelled', tone: 'chip--dashed' },
  TRIP_DELETED: { label: 'Trip deleted', tone: 'chip--grey' },
};

export function notificationKind(type: NotificationEventType): Kind {
  return KINDS[type] ?? { label: 'Update', tone: 'chip--muted' };
}

/**
 * Where opening a notification goes. Null when the trip is gone. A proposal
 * on the trip's proposals page gets a #proposal-N anchor so the page can
 * scroll to it; itinerary and invitation links are used as given.
 */
export function notificationLink(n: AppNotification): string | null {
  if (!n.action_url) return null;
  if (n.proposal_id !== null && /^\/trips\/\d+\/?$/.test(n.action_url)) {
    return `${n.action_url.replace(/\/$/, '')}#proposal-${n.proposal_id}`;
  }
  return n.action_url;
}

/** "Just now", "5m ago", "3h ago", "2d ago", then "Mar 4" (or "Mar 4, 2026"). */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const then = new Date(iso);
  const minutes = Math.floor((now - then.getTime()) / 60_000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const sameYear = then.getFullYear() === new Date(now).getFullYear();
  return then.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
  });
}

const ISO_INSTANT =
  /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})\b/g;

/**
 * Messages are plain text from the server and may include raw timestamps
 * ("before 2027-07-01T18:00:00+00:00"); show those in the viewer's time.
 */
export function readableMessage(message: string, timeZone?: string): string {
  return message.replace(ISO_INSTANT, (iso) => {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZone,
    });
  });
}

/** Every loaded notification, newest first. */
export function flattenPages(pages: NotificationPage[] | undefined) {
  return (pages ?? []).flatMap((page) => page.items);
}

/**
 * "Mark all read" stops at the newest notification on screen, so anything
 * that arrives while the user is reading stays unread.
 */
export function newestLoadedId(items: AppNotification[]): number | undefined {
  return items.reduce<number | undefined>(
    (max, n) =>
      max === undefined || n.notification_id > max ? n.notification_id : max,
    undefined,
  );
}
