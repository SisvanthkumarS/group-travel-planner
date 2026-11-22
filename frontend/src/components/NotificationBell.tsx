import { NavLink } from 'react-router-dom';
import { useUnreadCount } from '../api/hooks';
import { unreadBadge } from '../lib/notifications';

export function BellIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 9a6 6 0 1 1 12 0c0 5 2 6.5 2 6.5H4S6 14 6 9" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </svg>
  );
}

/** Header bell: unread count across the whole inbox, polled while visible. */
export function NotificationBell() {
  const { data } = useUnreadCount();
  const count = data?.unread_count ?? 0;
  const badge = unreadBadge(count);
  return (
    <NavLink
      to="/notifications"
      className="bell"
      aria-label={
        data === undefined
          ? 'Notifications'
          : count
            ? `Notifications, ${count} unread`
            : 'Notifications, none unread'
      }
    >
      <BellIcon />
      {badge && (
        <span className="bell__badge mono" aria-hidden="true">
          {badge}
        </span>
      )}
    </NavLink>
  );
}
