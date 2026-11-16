import { apiRequest } from './client';
import type {
  AppNotification,
  MarkAllReadRequest,
  MarkAllReadResponse,
  NotificationPage,
  NotificationPreferences,
  UnreadCount,
} from './types';

export const NOTIFICATIONS_PAGE_SIZE = 20;

/** Newest first. Pass the previous page's next_before_id to load older ones. */
export function listNotifications({
  beforeId,
  unreadOnly,
}: {
  beforeId?: number;
  unreadOnly: boolean;
}) {
  const params = new URLSearchParams({
    limit: String(NOTIFICATIONS_PAGE_SIZE),
  });
  if (beforeId !== undefined) params.set('before_id', String(beforeId));
  if (unreadOnly) params.set('unread_only', 'true');
  return apiRequest<NotificationPage>(`/notifications?${params}`);
}

export const getUnreadCount = () =>
  apiRequest<UnreadCount>('/notifications/unread-count');

export const markNotificationRead = (notificationId: number) =>
  apiRequest<AppNotification>(`/notifications/${notificationId}/read`, {
    method: 'PATCH',
  });

/** through_id leaves anything newer than what the user has seen unread. */
export const markAllNotificationsRead = (body: MarkAllReadRequest) =>
  apiRequest<MarkAllReadResponse>('/notifications/read-all', {
    method: 'POST',
    body,
  });

export const getNotificationPreferences = () =>
  apiRequest<NotificationPreferences>('/notifications/preferences');

export const saveNotificationPreferences = (body: NotificationPreferences) =>
  apiRequest<NotificationPreferences>('/notifications/preferences', {
    method: 'PUT',
    body,
  });
