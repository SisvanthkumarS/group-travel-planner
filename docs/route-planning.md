# Route planning proposal (draft)

Status: **Draft for team discussion.** Nothing in this document is implemented.
The approach is agreed; the open decisions in section 8 must be settled before
implementation starts.

## 1. Goal

In the shared trip chat, a member clicks **Plan my route**. The group receives a
message that explains how to travel between the day's approved activities, how
long each leg takes, and where the schedule is too tight. Each leg's route is
also returned as structured data, so the frontend can draw it on the itinerary map.

Approved itinerary times are fixed by group votes. Route planning therefore does
**not** reorder or reschedule activities. It plans travel between consecutive
activities in their existing order and reports conflicts.

### Non-goals for the first version

- Reordering, rescheduling, or proposing new activities.
- Live traffic, disruptions, or real-time arrivals.
- Ticket prices, travel passes, and last-train times. See section 9.
- Writing geocoded coordinates back to proposals.

## 2. Approach: the backend computes routes, the AI explains them

| Option                                       | Summary                                                                                         | Decision                     |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------- |
| A. AI web search only                        | Enable the provider's web search tool and ask the model for a route                             | Rejected                     |
| **B. Routing API + AI summary**              | Backend calls a routing provider for each leg, checks feasibility, then the AI writes a summary | **Chosen**                   |
| C. B plus web search for supplementary facts | B, plus web search for prices, passes, and service hours                                        | Possible phase 2 (section 9) |

Reasons for B:

- Travel times and lines must be accurate. Text that a model reads from web
  pages is not reliable enough and cannot be checked automatically.
- Feasibility ("Is there enough time between activities?") is a calculation,
  so it belongs in the backend, not the model.
- Routing APIs return route geometry the map can draw. Web search does not.
- Route data still works when the AI provider is missing or fails. The backend
  can fall back to a template summary.
- The current `chat_completions` mode has no web search tool; B works in both
  AI modes.

## 3. Flow

1. A member calls the endpoint for a trip and a trip-local date.
2. The backend loads that day's ACTIVE itinerary items, ordered by `starts_at`.
   With fewer than two items, it returns a message saying there is nothing to route.
3. **Locate each item.** Items created from an attraction or with a map pin
   already have coordinates. Items with only a `location` name are geocoded
   using the trip destination as a bias. Items that cannot be located are
   reported as `UNLOCATED`, and legs that involve them are skipped.
4. **Compute legs.** For each consecutive pair, the backend requests a route for
   each allowed mode. Departure time is the earlier activity's `ends_at`, because
   transit options depend on the time of day. It chooses the fastest successful
   mode, or follows a preference rule (section 8).
5. **Check feasibility.** For each leg, `gap = next.starts_at - previous.ends_at`:

   | Status     | Rule                                       |
   | ---------- | ------------------------------------------ |
   | `OK`       | travel time + buffer ≤ gap                 |
   | `TIGHT`    | travel time ≤ gap < travel time + buffer   |
   | `CONFLICT` | travel time > gap                          |
   | `OVERLAP`  | gap < 0; the activities overlap in time    |
   | `UNROUTED` | an endpoint is unlocated or no route found |

   The default buffer is an open decision. 10 minutes is a reasonable start.

6. **Summarize.** The structured result goes to the AI with a dedicated prompt.
   The AI writes a short explanation in the group's language. It must not change
   any numbers. If the AI is unavailable, the backend writes a template summary.
7. **Publish.** The summary and structured route are saved as an assistant
   message in the shared chat, linked to the member's request.

## 4. Backend changes

| Area                              | Change                                                                                                                                                                                                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/RoutingClient.py`           | New `RoutingClient` protocol with `route(origin, destination, mode, departure_time)` and `geocode(text, bias)`. One adapter per provider, using the same pattern as `AiChatClient`. A fake client is used in tests.                                                             |
| `core/config.py`                  | `ROUTING_PROVIDER`, `ROUTING_API_KEY`, `ROUTING_TIMEOUT_SECONDS`, `ROUTE_DEFAULT_MODES`, `ROUTE_BUFFER_MINUTES`. Route planning returns 503 when no provider is configured.                                                                                                     |
| `services/RouteService.py`        | Steps 2 to 5: locating, leg routing, and feasibility. It does not depend on the AI and can be tested on its own.                                                                                                                                                                |
| `services/AiChatService.py`       | New `plan_route` entry point. It reuses the shared chat's rules: membership check, at most one active AI reply per room (409), stale placeholder recovery, and marking failures `FAILED`. Routing and AI calls run outside the database transaction, as AI generation does now. |
| `core/AiChatClient.py`            | New `summarize_route(route, trip_context)` method with its own instructions. It returns text only and never creates a proposal draft.                                                                                                                                           |
| `controllers/AiChatController.py` | New route (section 5).                                                                                                                                                                                                                                                          |
| Migration `0013`                  | Add nullable `route JSONB` to `chat_messages`.                                                                                                                                                                                                                                  |
| `schemas/AiChat.py`               | Add `route` (nullable) to shared message responses.                                                                                                                                                                                                                             |
| Docs and tests                    | OpenAPI regeneration, API guide section, and tests with a fake routing client and a fake AI client.                                                                                                                                                                             |

Coordinates and the API key stay on the server. Only activity coordinates or
location names are sent to the routing provider, not member names or messages.

## 5. API draft

**`POST /api/v1/trips/{trip_id}/chat/plan-route`** · Trip members · Success: **201**

```json
{
  "date": "2030-07-12",
  "modes": ["TRANSIT", "WALK"]
}
```

| Field   | Required | Rules                                                            |
| ------- | -------- | ---------------------------------------------------------------- |
| `date`  | Yes      | Trip-local date within the trip dates                            |
| `modes` | No       | Subset of the supported modes; defaults to `ROUTE_DEFAULT_MODES` |

The response has the same shape as Ask AI: the member's request message and the
assistant reply. The assistant message includes `route`:

```json
{
  "date": "2030-07-12",
  "timezone": "America/New_York",
  "provider": "google",
  "stops": [
    {
      "item_id": 11,
      "title": "Museum of Modern Art",
      "latitude": 40.7614,
      "longitude": -73.9776,
      "located_by": "PROPOSAL"
    },
    {
      "item_id": 12,
      "title": "9/11 Memorial & Museum",
      "latitude": 40.7115,
      "longitude": -74.0134,
      "located_by": "PROPOSAL"
    }
  ],
  "legs": [
    {
      "from_item_id": 11,
      "to_item_id": 12,
      "mode": "TRANSIT",
      "departure_at": "2030-07-12T12:30:00-04:00",
      "duration_seconds": 1500,
      "distance_meters": 6900,
      "gap_seconds": 1800,
      "status": "OK",
      "polyline": "encoded polyline",
      "steps": [
        {
          "mode": "WALK",
          "instruction": "Walk to 5 Av/53 St",
          "duration_seconds": 240
        },
        {
          "mode": "TRANSIT",
          "line": "E",
          "from_stop": "5 Av/53 St",
          "to_stop": "World Trade Center",
          "stops": 6,
          "duration_seconds": 1020
        }
      ]
    }
  ],
  "warnings": []
}
```

`located_by` is `PROPOSAL` for saved coordinates, `GEOCODED` for coordinates the
service looked up, or `UNLOCATED` for items without coordinates.

| Status | When                                                                                 |
| ------ | ------------------------------------------------------------------------------------ |
| 403    | Not a trip member                                                                    |
| 404    | Trip not found                                                                       |
| 409    | Another AI reply in this room is still generating                                    |
| 422    | Invalid date or mode                                                                 |
| 503    | No routing provider configured                                                       |
| 502    | Routing provider failed for every leg. Partial failures are `UNROUTED` legs instead. |

## 6. Routing providers

All candidates return route geometry, distance, duration, and step instructions.
None returns a map image; the frontend draws the geometry with a map library.

| Provider               | Walk / drive / cycle | Public transit                           | Coverage                                  |
| ---------------------- | -------------------- | ---------------------------------------- | ----------------------------------------- |
| Google Routes API      | Yes                  | Yes                                      | Most countries except mainland China      |
| AMap (高德)            | Yes                  | Yes                                      | Mainland China                            |
| Mapbox Directions      | Yes                  | No                                       | Global                                    |
| OpenRouteService       | Yes                  | Not documented in the sources we checked | Global, OpenStreetMap roads               |
| Transitous (MOTIS API) | Yes                  | Yes                                      | Global, wherever open transit feeds exist |

### Free usage (checked November 2026; confirm in each console before use)

| Provider         | Free allowance                                                                              | Payment card                                 | Notes                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Google Routes    | Per SKU per month: 10,000 Essentials, 5,000 Pro. Then about $5 to $10 per 1,000             | Required (billing account)                   | Replaced the old $200 monthly credit in March 2025. Requested fields decide the SKU. Set budget alerts and quotas. |
| Mapbox           | 10,000 Directions requests per month without a payment method                               | Not required                                 | Some third-party guides say 100,000; the official docs say 10,000                                                  |
| OpenRouteService | Free key, about 2,000 directions requests per day, 40 per minute                            | Not required                                 | A later forum post reports higher quotas. Free by design                                                           |
| AMap             | Individual verified developers: 150,000 basic requests per month, including transit routing | Not required; identity verification required | New pricing since May 2025. Third-party figures vary widely                                                        |
| Transitous       | Free                                                                                        | Not required                                 | Volunteer-run, best effort; may stop serving any client. Not suitable when uptime matters                          |
| Self-hosted      | Software is free (OSRM, OpenTripPlanner, MOTIS)                                             | Not required                                 | Requires servers and map/transit data imports                                                                      |

### Expected usage

A one-day plan usually has 3 to 6 legs, and each leg needs one request per mode
tried. Even 1,000 plans per month with two modes is roughly 10,000 requests, so
cost is not the deciding factor for this project. Transit support and the need
for a payment card are.

### Recommendation

- **Default:** Google Routes. The bundled attractions are in New York, transit
  data is strong, and the free allowance is enough. It requires a billing account.
- **No payment card:** Transitous for transit and OpenRouteService for walking
  and driving, accepting that Transitous may be unavailable during a demo.
- **Mainland China later:** add an AMap adapter. `RoutingClient` lets each trip
  or deployment choose a provider.

## 7. Failure handling

- Each provider call has a timeout. Legs are requested concurrently within an
  overall budget so one slow leg does not block the reply.
- A failed leg becomes `UNROUTED` with a warning; the rest of the plan is kept.
- If the AI fails or is not configured, the reply uses a template summary built
  from the same data, so the button still produces a useful result.
- Itinerary changes after the plan are not reflected automatically. The message
  shows when the plan was generated, and members can plan again.

## 8. Open decisions

| #   | Question                            | Options                                                         | Current suggestion                       |
| --- | ----------------------------------- | --------------------------------------------------------------- | ---------------------------------------- |
| 1   | Routing provider                    | Google / Transitous + OpenRouteService / AMap                   | Google                                   |
| 2   | Planning scope                      | One day / the whole trip                                        | One day                                  |
| 3   | Start and end point                 | None / optional hotel or start address in the request           | Decide with the team                     |
| 4   | Travel modes                        | Transit + walk / also drive or taxi / user-selected             | Transit + walk by default                |
| 5   | Mode choice per leg                 | Fastest / walk when under N minutes / always the requested mode | Walk when under 15 minutes, else fastest |
| 6   | Where results go                    | Shared chat for everyone / private response to the requester    | Shared chat                              |
| 7   | Feasibility buffer                  | Fixed minutes / configurable                                    | 10 minutes, configurable                 |
| 8   | Geocoding items without coordinates | Geocode automatically / skip and ask members to pin             | Geocode, but do not write back           |
| 9   | Who may trigger planning            | Any member / organizer only                                     | Any member                               |

## 9. Possible phase 2: supplementary web search

After route data is stable, the summary step could use the AI provider's web
search tool for facts a routing API does not provide: fares, passes, service
hours, and accessibility notes. Search results would be labeled as approximate,
include their sources, and never override computed times. The Responses adapter
already requests `web_search_call.action.sources`, but no tool is enabled yet.

## 10. Sources

- [Google Maps Platform pricing](https://mapsplatform.google.com/pricing/)
- [Google Routes API pricing in 2026 (scrap.io)](https://scrap.io/google-routes-api-pricing)
- [Is Google Maps API free in 2026? (Woosmap)](https://www.woosmap.com/blog/is-google-maps-api-free)
- [Mapbox account sign-up limits](https://docs.mapbox.com/accounts/guides/signup/)
- [Mapbox pricing (StoreRocket)](https://storerocket.io/learn/mapbox-pricing)
- [Openrouteservice plans](https://openrouteservice.org/plans/)
- [Openrouteservice updated API quotas](https://ask.openrouteservice.org/t/updated-api-quotas/500)
- [AMap service upgrade and quotas](https://lbs.amap.com/upgrade)
- [Transitous API](https://transitous.org/api/)
- [MOTIS project](https://github.com/motis-project/motis)
