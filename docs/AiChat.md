# AI chat backend

All routes use the `/api/v1` prefix and existing cookie authentication.
For POST, PATCH and DELETE, send `X-CSRF-Protection: 1`.

## Shared Trip chat

Every Trip has one shared conversation available to its current members. Reading
an unused room returns an empty message page. The first successful send creates
the room automatically.

| Method | Path                                      | Request                                                | Success                        |
| ------ | ----------------------------------------- | ------------------------------------------------------ | ------------------------------ |
| GET    | `/trips/{trip_id}/chat/messages`          | Optional `before_id` and `limit` (default 30, max 100) | 200, message page              |
| POST   | `/trips/{trip_id}/chat/messages`          | `{"content":"Meet in the lobby"}`                      | 201, member message            |
| POST   | `/trips/{trip_id}/chat/ask-ai`            | `{"content":"What should we do next?"}`                | 201, question and AI reply     |
| GET    | `/trips/{trip_id}/chat/context`           | No body                                                | 200, Trip and active itinerary |
| PATCH  | `/trips/{trip_id}/chat/drafts/{draft_id}` | `{"decision":"ACCEPT"}` or `{"decision":"REJECT"}`     | 200, updated draft             |

Messages identify their author with `role` and `user_id`. AI replies have
`role: "ASSISTANT"`, `user_id: null`, and a `reply_to_message_id` that points to
the member's question. The message page is newest first and returns
`next_before_id` for older pages.

Ordinary messages are saved locally. An explicit AI question sends the latest
Trip and itinerary plus a snapshot of up to 20 completed messages from before
the question was saved. Messages sent during generation appear in the room and
can be included in later AI calls. The room allows one active AI reply at a
time. A concurrent AI request returns 409. Ordinary messages remain available
throughout generation and when the provider is unavailable.

All members can view PENDING drafts. The member who asked AI can accept or reject
the draft. Shared drafts include `asked_by_user_id` in history, Ask AI, and PATCH
responses. Its value is the original question's author ID, or `null` if that
author is unavailable. Show decision buttons for a PENDING draft when the ID
matches the signed-in member. The server checks permission on every decision.
Accepted activities enter the existing Proposal workflow.

## Provider configuration

Set the following values in the repository root `.env` for a local backend, or
in `docker/.env` for Docker Compose.

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_MODE=responses
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=30
```

For another OpenAI-compatible provider, set its API key, API root (such as
`https://provider.example/v1`), and model ID. The SDK appends the route path.
Use `responses` for Responses API Structured Outputs or `chat_completions`
for a Chat Completions endpoint supporting JSON mode. Both modes validate the
reply against the same backend schema. To apply changes in Docker, recreate
the backend service with
`docker compose --env-file docker/.env -f docker/compose.dev.yml up -d backend`.

In Chat Completions mode, earlier assistant messages are wrapped in the reply's
JSON format when building model history. If a completed model answer contains
blank, malformed, or schema-invalid JSON, the adapter retries once with clearer
formatting instructions within the original timeout budget. A second invalid
answer follows the existing 502 failure path.

## Legacy private chats

The following routes are deprecated. Existing private conversations stay
accessible to their original owners.

| Method | Path                                 | Request                                                    | Success contract                                                     |
| ------ | ------------------------------------ | ---------------------------------------------------------- | -------------------------------------------------------------------- |
| POST   | `/trips/{trip_id}/chats`             | `{"title":"Weekend plan"}`; use `{}` for the default title | 201, chat                                                            |
| GET    | `/trips/{trip_id}/chats`             | No body                                                    | 200, current user's chats, most recently updated first               |
| GET    | `/chats/{chat_id}/context`           | No body                                                    | 200, current Trip and active itinerary used by AI                    |
| GET    | `/chats/{chat_id}/messages`          | Optional `before_id` and `limit` (default 30, max 100)     | 200, `messages` newest first plus `next_before_id`                   |
| POST   | `/chats/{chat_id}/messages`          | `{"content":"Plan my weekend"}`                            | 201, `user_message` and `assistant_message` with an optional `draft` |
| PATCH  | `/chats/{chat_id}/drafts/{draft_id}` | `{"decision":"ACCEPT"}` or `{"decision":"REJECT"}`         | 200, draft with status and `proposal_ids`                            |
| DELETE | `/chats/{chat_id}`                   | No body                                                    | 204, no body                                                         |

The context endpoint is available to the chat owner while they are a Trip
member. It returns the Trip name, destination, travel dates, timezone, current
time, and active itinerary activities with their titles, descriptions, locations,
estimated costs, and start and end times. Trips with no active activities return
`"itinerary": []`. Every message automatically includes a fresh copy of this
context in the model request. The frontend can call the GET endpoint to display
what the model sees. The context is read from the Trip and is kept out of the
saved message history.

A `PROPOSAL` draft has exactly one proposal; an `ITINERARY` draft has at least two.
Each item uses the existing `CreateProposalRequest` fields. Store validated drafts
with `model_dump(mode="json")` so dates and decimal costs are JSON serializable.
Drafts belong to their source messages, one per message. Only attach drafts to
assistant messages. The proposal link table records submission results. Deleting a
chat deletes its messages, drafts and links; it does not delete submitted proposals.

Sending commits the user message and the assistant's `GENERATING` placeholder
before calling the provider. On success, a new transaction saves the reply and any
`PENDING` draft. A second send in the same chat returns 409 while the prior reply
is generating. Retry after that reply finishes. A send can recover a placeholder
older than five minutes or twice the configured provider timeout, whichever is
longer.

Before saving a draft, the backend checks the Trip dates, proposal capacity, and
overlaps within the draft and against the active itinerary. An invalid schedule
returns 502, and insufficient proposal capacity returns 409. Provider errors,
invalid drafts and timeouts leave the user message in history and mark the
assistant reply as `FAILED`. A timeout returns 504. A missing provider returns
503 before saving either message.

- Require current trip membership for all operations and look up chats by the
  authenticated owner. A user ID or proposal body is never supplied by the client
  when confirming a draft. Get the trip from the authorized chat.
- The OpenAI adapter sends recent chat history and the current trip context to
  the Responses API and parses the result as `AiChatModelReply`.
- For draft decisions, only the chat owner who is still a trip member can act.
  Acceptance revalidates the whole batch against current trip dates, timezone,
  the active itinerary and the 100-proposal limit, then commits the new
  `PENDING` proposals, their links, and the draft decision together.
  Invalid proposals return 422. An over-limit batch
  returns 409. Rejection records the decision without creating proposals.
  Repeating the same decision returns the existing result. Attempting to reverse
  it returns 409. Accepted proposals follow the existing Organizer-initiated
  voting workflow.
