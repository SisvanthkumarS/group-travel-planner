# Frontend handoff: notifications

Backend and generated API types are ready. Build the UI using the existing
`apiRequest` helper (cookies and CSRF header are already handled).

1. Add authenticated `/notifications`, a header bell/unread badge, All/Unread
   filters, and a “Load more” button. Fetch `GET /notifications?limit=20` and use
   `next_before_id` as `before_id` for subsequent pages. Reset pagination on filter
   changes; refetch the first page for new events.
2. Render `title`, `message`, `trip_name`, and `created_at` as text. Null `read_at`
   means unread. Follow `action_url` when present; null means no link. Use
   `proposal_id`/`invitation_id` to focus an item. Invitation links lead to `/trips`.
3. On opening an item, call `PATCH /notifications/{id}/read`. For “Mark all read,”
   call `POST /notifications/read-all` with `{through_id: newestLoadedId}` (or `{}`
   to mark the entire inbox). Invalidate the list and unread count after success.
4. Add two independent switches from `GET /notifications/preferences`. Save both
   via `PUT /notifications/preferences`:

   ```json
   { "in_app_enabled": true, "email_enabled": false }
   ```

   Defaults are in-app on/email off. Show saving/error feedback and confirm the
   returned values. Turning off in-app updates keeps old history. Email opt-out
   cancels queued sends; enabling a channel never fills in past notifications.

5. Poll `GET /notifications/unread-count` and the visible first page about every
   20 seconds while signed in and visible; refresh on tab focus. Stop on sign-out
   and clear user-specific caches. Add loading, empty, error/retry, and disabled
   control states.

No notification UI is implemented in this backend change. Apply migration `0008`
before testing. To test email, the operator must configure Hostinger SMTP and set
`EMAIL_ENABLED=true`; user opt-in alone cannot enable the server transport.
Full contracts, event types, and examples: [notifications.md](notifications.md).
