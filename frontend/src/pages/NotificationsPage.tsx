import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotificationPreferences,
  useNotifications,
  useSaveNotificationPreferences,
  useUnreadCount,
} from '../api/hooks';
import type { AppNotification, NotificationPreferences } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { QueryError } from '../components/bits';
import {
  flattenPages,
  newestLoadedId,
  notificationKind,
  notificationLink,
  readableMessage,
  timeAgo,
} from '../lib/notifications';

const errorText = (e: unknown, fallback: string) =>
  e instanceof Error ? e.message : fallback;

/** Opening an item marks it read, then follows its link if the trip still exists. */
function NotificationRow({ item }: { item: AppNotification }) {
  const navigate = useNavigate();
  const markRead = useMarkNotificationRead();
  const unread = item.read_at === null;
  const link = notificationLink(item);
  const kind = notificationKind(item.event_type);

  function open() {
    if (unread) markRead.mutate(item.notification_id);
    if (link) navigate(link);
  }

  const body = (
    <>
      <span className="note__dot" aria-hidden="true" />
      <span className="note__body">
        <span className="note__top">
          <span className={`chip ${kind.tone}`}>{kind.label}</span>
          <span className="note__trip">{item.trip_name}</span>
          <time className="note__time mono" dateTime={item.created_at}>
            {timeAgo(item.created_at)}
          </time>
        </span>
        <span className="note__title">
          {unread && <span className="visually-hidden">Unread: </span>}
          {item.title}
        </span>
        <span className="note__message">{readableMessage(item.message)}</span>
        {!item.action_url && (
          <span className="note__gone">This trip no longer exists.</span>
        )}
        {markRead.error && (
          <span className="field__error" role="alert">
            {errorText(markRead.error, 'Could not mark this read.')}
          </span>
        )}
      </span>
      {link && (
        <span className="note__go" aria-hidden="true">
          →
        </span>
      )}
    </>
  );

  return (
    <li className={`note${unread ? ' note--unread' : ''}`}>
      {link || unread ? (
        <button
          type="button"
          className="note__open"
          onClick={open}
          disabled={markRead.isPending}
        >
          {body}
        </button>
      ) : (
        <div className="note__open">{body}</div>
      )}
    </li>
  );
}

function Switch({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="switch">
      <input
        type="checkbox"
        role="switch"
        className="switch__input"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch__track" aria-hidden="true" />
      <span className="switch__text">
        <span className="switch__label">{label}</span>
        <span className="switch__desc">{description}</span>
      </span>
    </label>
  );
}

/** Two independent channels; each toggle saves both and shows what was saved. */
function NotificationSettings() {
  const { user } = useAuth();
  const prefs = useNotificationPreferences();
  const save = useSaveNotificationPreferences();
  const [saved, setSaved] = useState(false);

  function change(next: Partial<NotificationPreferences>) {
    if (!prefs.data) return;
    setSaved(false);
    save.mutate(
      { ...prefs.data, ...next },
      { onSuccess: () => setSaved(true) },
    );
  }

  return (
    <section className="card" aria-labelledby="note-settings-title">
      <h2 id="note-settings-title" className="card__title">
        How you hear about updates
      </h2>
      {prefs.error ? (
        <QueryError error={prefs.error} onRetry={() => prefs.refetch()} />
      ) : !prefs.data ? (
        <p className="muted small" role="status">
          Loading settings…
        </p>
      ) : (
        <>
          <Switch
            label="In the app"
            description="Show updates here and on the bell."
            checked={prefs.data.in_app_enabled}
            disabled={save.isPending}
            onChange={(on) => change({ in_app_enabled: on })}
          />
          <Switch
            label="Email"
            description={
              user
                ? `Also email them to ${user.email}.`
                : 'Also email them to you.'
            }
            checked={prefs.data.email_enabled}
            disabled={save.isPending}
            onChange={(on) => change({ email_enabled: on })}
          />
          {!prefs.data.in_app_enabled && (
            <p className="small muted">
              New updates won't show here. What's already in your inbox stays.
            </p>
          )}
          <p className="small muted" role="status" aria-live="polite">
            {save.isPending ? 'Saving…' : saved ? 'Saved.' : ''}
          </p>
          {save.error && (
            <div className="form-error" role="alert">
              {errorText(save.error, 'Could not save your settings.')} Your
              settings are unchanged.
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** Notifications inbox: All/Unread, mark all read, load more, and settings. */
export function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const list = useNotifications(unreadOnly);
  const unread = useUnreadCount();
  const markAll = useMarkAllNotificationsRead();
  const items = flattenPages(list.data?.pages);
  const unreadCount = unread.data?.unread_count ?? 0;

  // The badge polls on its own timer; when it goes up, pull the new items in
  // now instead of waiting for the list's next poll.
  const seenCount = useRef(unreadCount);
  const { refetch } = list;
  useEffect(() => {
    if (unreadCount > seenCount.current) void refetch();
    seenCount.current = unreadCount;
  }, [unreadCount, refetch]);

  return (
    <main className="page">
      <div className="page__header page__header--row">
        <div>
          <h1 className="page__title">Notifications</h1>
          <p className="page__subtitle">
            Invitations, votes and itinerary changes across your trips.
          </p>
        </div>
        <button
          type="button"
          className="btn btn--secondary"
          onClick={() => markAll.mutate(newestLoadedId(items))}
          disabled={markAll.isPending || unreadCount === 0 || !items.length}
        >
          {markAll.isPending ? 'Marking…' : 'Mark all read'}
        </button>
      </div>

      <div className="trip-body">
        <section className="trip-main" aria-label="Notifications">
          <div className="tabs" role="group" aria-label="Show">
            {[false, true].map((only) => (
              <button
                key={String(only)}
                type="button"
                className={`tabs__tab${unreadOnly === only ? ' active' : ''}`}
                aria-pressed={unreadOnly === only}
                onClick={() => setUnreadOnly(only)}
              >
                {only ? 'Unread' : 'All'}
                {only && unreadCount > 0 && (
                  <span className="tabs__count"> {unreadCount}</span>
                )}
              </button>
            ))}
          </div>

          {markAll.error && <QueryError error={markAll.error} />}

          {list.error && !list.data ? (
            <QueryError error={list.error} onRetry={() => list.refetch()} />
          ) : list.isPending ? (
            <p className="muted" role="status">
              Loading notifications…
            </p>
          ) : items.length === 0 ? (
            <p className="empty">
              {unreadOnly
                ? "You're all caught up."
                : "Nothing yet. You'll hear about invitations, votes and itinerary changes here."}
            </p>
          ) : (
            <>
              <ul className="notes">
                {items.map((item) => (
                  <NotificationRow key={item.notification_id} item={item} />
                ))}
              </ul>
              {list.isFetchNextPageError && (
                <QueryError
                  error={list.error}
                  onRetry={() => list.fetchNextPage()}
                />
              )}
              {list.hasNextPage && (
                <button
                  type="button"
                  className="btn btn--secondary notes__more"
                  onClick={() => list.fetchNextPage()}
                  disabled={list.isFetchingNextPage}
                >
                  {list.isFetchingNextPage ? 'Loading…' : 'Load more'}
                </button>
              )}
            </>
          )}
        </section>

        <aside className="trip-aside">
          <NotificationSettings />
        </aside>
      </div>
    </main>
  );
}
