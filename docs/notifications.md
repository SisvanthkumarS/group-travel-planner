# Notification API and delivery

Apply migration `0008` (`pnpm run db:migrate`) before starting the updated backend.
It adds user preferences, notification history, and a durable email outbox.
Existing and new accounts default to in-app notifications **on** and email **off**.
This release includes backend APIs only; see the [frontend handoff](frontend-notifications.md).

All paths below are relative to `/api/v1`. Authentication uses the existing session
cookies. Mutations require `X-CSRF-Protection: 1`; browser origins must be trusted
by `CORS_ORIGINS`. Every operation uses the signed-in user's identity, never a
caller-supplied recipient ID. The complete schemas are in [openapi.yaml](openapi.yaml)
and live Swagger `/docs`.

## Endpoints

| Method and path                               | Request                                                                                  | Response                                            |
| --------------------------------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `GET /notifications`                          | `limit` 1–100 (default 20), optional positive `before_id`, `unread_only` (default false) | `{items: [...], next_before_id: number \| null}`    |
| `GET /notifications/unread-count`             | None                                                                                     | `{unread_count: number}`                            |
| `GET /notifications/preferences`              | None                                                                                     | `{in_app_enabled: boolean, email_enabled: boolean}` |
| `PUT /notifications/preferences`              | Both booleans required                                                                   | Saved preferences                                   |
| `PATCH /notifications/{notification_id}/read` | No body                                                                                  | Updated notification                                |
| `POST /notifications/read-all`                | `{}` or `{through_id: number}`                                                           | `{updated_count: number}`                           |
| `POST /notifications/test-email`              | No body; diagnostic flags required                                                       | `{status: "accepted", message_id: string}`          |

All successful operations above return HTTP 200. Missing authentication is 401;
CSRF failure is 403; invalid inputs are 422. A missing, other user's, or email-only
notification is 404 on the mark-read endpoint, avoiding disclosure of ownership.
Preferences reject nulls, strings in place of booleans, omitted fields, and unknown
fields. Reading notification history never changes read status.

### Notification list

```json
{
  "items": [
    {
      "notification_id": 42,
      "event_type": "POLL_OPENED",
      "title": "Voting is open",
      "message": "Vote on Museum in NYC weekend before 2027-07-01T18:00:00+00:00.",
      "trip_name": "NYC weekend",
      "trip_id": 12,
      "proposal_id": 9,
      "invitation_id": null,
      "created_at": "2027-06-30T12:00:00Z",
      "read_at": null,
      "action_url": "/trips/12"
    }
  ],
  "next_before_id": 42
}
```

Items are ordered by descending notification ID. Send `next_before_id` as
`before_id` to load the next page, keeping the same filter; null means no next page.
New updates are found by fetching the first page again. The unread count covers
the entire inbox, independently of pagination. Treat null `read_at` as unread;
timestamps include their timezone and can be displayed in the viewer's timezone.

`action_url` is a relative app route. Invitation-received messages point to
`/trips` (the invitation inbox); other updates point to the trip or its itinerary.
Use `proposal_id` or `invitation_id` to focus the matching item if supported by the
frontend. These IDs may become null when the underlying resource is deleted.
Deleting a trip preserves message text and its captured name, sets related IDs to
null through foreign keys, and returns `action_url: null`. Resource APIs continue
to enforce their own authorization.

### Preferences

```json
{ "in_app_enabled": true, "email_enabled": false }
```

The two channels are independent:

| In-app | Email | Effect on future events                                      |
| ------ | ----- | ------------------------------------------------------------ |
| On     | Off   | Inbox entry only                                             |
| Off    | On    | Email only; no visible inbox entry or unread badge increment |
| On     | On    | Inbox entry and queued email                                 |
| Off    | Off   | No notification created                                      |

Settings persist across sessions. Disabling in-app notifications preserves old
history and its read state. Enabling a channel does not backfill earlier events.
Disabling email cancels pending and claimed jobs; enabling it again does not
revive those jobs. A message already being submitted to SMTP may still arrive
and cannot be recalled. Preference updates do not wait for SMTP network calls.

The server's `EMAIL_ENABLED` flag is a separate operator control. Users can save
their email preference even while SMTP delivery is paused. Emails queued while
the server is paused are delivered when it resumes, if the user's preference
still permits them. For Hostinger configuration see [email setup](email-notifications.md).

### Read state

Marking an item read is idempotent and preserves its first `read_at`. For “mark
all read,” send `through_id` equal to the newest loaded notification ID to leave
newer incoming messages unread. Sending `{}` marks all unread visible rows at the
time of the update. Neither action changes another user's inbox or email delivery.

## Events and recipients

| `event_type`                                  | Trigger                                       | Recipients                       |
| --------------------------------------------- | --------------------------------------------- | -------------------------------- |
| `INVITATION_RECEIVED`                         | Invitation created                            | Invitee                          |
| `INVITATION_ACCEPTED` / `INVITATION_DECLINED` | Invitation answered                           | Inviter                          |
| `PROPOSAL_CREATED`                            | Activity proposed                             | Organizer                        |
| `POLL_OPENED`                                 | Organizer opens voting                        | Eligible voter snapshot          |
| `POLL_TIED`                                   | Scheduled closure finds a tie                 | Organizer                        |
| `ACTIVITY_APPROVED` / `ACTIVITY_REJECTED`     | Scheduled outcome or organizer tie resolution | Current trip members             |
| `ACTIVITY_CANCELLED`                          | Itinerary item canceled                       | Current trip members             |
| `TRIP_DELETED`                                | Organizer deletes trip                        | Members captured before deletion |

The actor is excluded from their own action notifications. Scheduler events have
no actor, so the organizer and proposal author receive them when applicable.
Approval and itinerary insertion produce one combined notification. Individual
votes and withdrawn proposals do not generate notifications in this version.

## Persistence and background email delivery

`NotificationPublisher` writes event/recipient records and outbox jobs in the
existing business transaction; failures roll back the action and its notifications
together. A unique `(user_id, event_key)` prevents duplicate records for the same
event. Existing trip locks and workflow state transitions protect scheduled and
manual retries. Publication never calls SMTP.

The FastAPI lifespan starts an email worker when SMTP and the worker are enabled.
It scans the database, claims a bounded batch with short locks, commits the claim,
then sends outside the transaction. Another API worker skips active claims.
Expired claims are recoverable after a crash; ownership tokens prevent an old
worker from overwriting a newer worker's result. Preferences are checked at claim
time, and cancellation is checked again before submission.

| Variable                              | Default | Purpose                                                                |
| ------------------------------------- | ------- | ---------------------------------------------------------------------- |
| `EMAIL_ENABLED`                       | `false` | Global SMTP delivery switch; in-app notifications still work           |
| `NOTIFICATION_EMAIL_WORKER_ENABLED`   | `true`  | Start the background worker                                            |
| `NOTIFICATION_EMAIL_INTERVAL_SECONDS` | `5`     | Scan interval                                                          |
| `NOTIFICATION_EMAIL_BATCH_SIZE`       | `20`    | Maximum candidates per scan                                            |
| `NOTIFICATION_EMAIL_MAX_ATTEMPTS`     | `5`     | Attempt limit including recovered claims                               |
| `NOTIFICATION_EMAIL_RETRY_SECONDS`    | `60`    | Initial retry delay, doubled per failure up to one hour                |
| `NOTIFICATION_EMAIL_LEASE_SECONDS`    | `600`   | Claim lifetime; minimum 120 seconds; keep above expected send duration |
| `EMAIL_TIMEOUT_SECONDS`               | `10`    | Timeout per SMTP socket operation                                      |

SMTP errors are sanitized. Outbox statuses are `PENDING`, `SENDING`, `SENT`,
`FAILED`, and `CANCELED`; attempt counts and generic failure reasons are stored
for operator inspection. There is no public delivery-admin API. `SENT` means SMTP
acceptance, not inbox delivery. `CANCELED` prevents further attempts but cannot
recall a message already being submitted.

SMTP has no exactly-once guarantee: a connection failure after acceptance, a crash
before saving success, or an expired claim during an unusually long send may
produce duplicates on retry. This version has no bounce/webhook tracking or
mailbox verification. It uses registered account addresses and explicit email
opt-in. Keep the diagnostic test-email endpoint disabled outside controlled tests;
it is synchronous and intentionally bypasses notification preferences.
