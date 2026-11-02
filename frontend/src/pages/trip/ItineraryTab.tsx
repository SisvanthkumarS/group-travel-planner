import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useCancelActivity, useItinerary, useProposals } from '../../api/hooks';
import type { ItineraryItem, Proposal } from '../../api/types';
import { QueryError } from '../../components/bits';
import { ConfirmDialog } from '../../components/Modal';
import {
  clock,
  countdown,
  eachDay,
  localDateKey,
  money,
  parseDateOnly,
  shortDate,
  weekday,
} from '../../lib/format';
import { useNow, useTripContext } from './context';

type Day = { key: string; items: ItineraryItem[]; voting: Proposal[] };

/** Group items by local calendar day across the whole trip, plus any stragglers. */
export function groupByDay(
  items: ItineraryItem[],
  voting: Proposal[],
  start: string,
  end: string,
): Day[] {
  const days = new Map<string, Day>();
  for (const key of eachDay(start, end))
    days.set(key, { key, items: [], voting: [] });
  const dayFor = (iso: string) => {
    const key = localDateKey(iso);
    if (!days.has(key)) days.set(key, { key, items: [], voting: [] });
    return days.get(key)!;
  };
  for (const item of items) dayFor(item.starts_at).items.push(item);
  for (const p of voting) dayFor(p.starts_at).voting.push(p);
  return [...days.values()].sort((a, b) => a.key.localeCompare(b.key));
}

function provenance(proposal: Proposal | undefined): string | null {
  const poll = proposal?.poll;
  if (!poll) return null;
  if (poll.outcome === 'TIED')
    return `APPROVED BY ORGANIZER · TIE ${poll.yes_count}–${poll.no_count}`;
  return `APPROVED ${poll.yes_count}–${poll.no_count}`;
}

/** US-15 and US-16: approved activities in time order; organizer can cancel one. */
export function ItineraryTab() {
  const { trip, viewer } = useTripContext();
  const itinerary = useItinerary(trip.trip_id);
  const proposals = useProposals(trip.trip_id);
  const cancel = useCancelActivity(trip.trip_id);
  const now = useNow();
  const [cancelling, setCancelling] = useState<ItineraryItem | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);

  if (itinerary.error)
    return (
      <QueryError error={itinerary.error} onRetry={() => itinerary.refetch()} />
    );
  if (itinerary.isPending)
    return (
      <p className="muted" role="status">
        Loading itinerary…
      </p>
    );

  const byId = new Map((proposals.data ?? []).map((p) => [p.proposal_id, p]));
  const voting = (proposals.data ?? []).filter((p) => p.status === 'OPEN');
  const days = groupByDay(
    itinerary.data,
    voting,
    trip.start_date,
    trip.end_date,
  );
  const total = itinerary.data.reduce(
    (sum, i) => sum + Number(i.estimated_cost || 0),
    0,
  );

  async function confirmCancel() {
    if (!cancelling) return;
    setCancelError(null);
    try {
      await cancel.mutateAsync(cancelling.item_id);
      setCancelling(null);
    } catch (e) {
      setCancelError(
        e instanceof Error ? e.message : 'Could not cancel the activity.',
      );
    }
  }

  return (
    <div className="itinerary">
      <div className="itinerary__summary">
        <p className="muted">
          Activities appear here once their poll is approved, in time order.
        </p>
        <span className="itinerary__total">
          Est. <strong className="mono">{money(total)}</strong> per traveler ·{' '}
          {itinerary.data.length}{' '}
          {itinerary.data.length === 1 ? 'activity' : 'activities'}
        </span>
      </div>

      <ol className="days">
        {days.map((day) => {
          const date = parseDateOnly(day.key);
          return (
            <li key={day.key} className="day">
              <div className="day__label">
                <span className="mono eyebrow">{weekday(date)}</span>
                <span className="day__date">{shortDate(date)}</span>
              </div>
              <div className="day__items">
                {day.items.length === 0 && day.voting.length === 0 && (
                  <span className="muted">Nothing scheduled yet.</span>
                )}
                {day.items.map((item) => (
                  <article
                    key={item.item_id}
                    className="activity"
                    aria-labelledby={`item-${item.item_id}`}
                  >
                    <div className="activity__time">
                      <span className="mono activity__start">
                        {clock(item.starts_at)}
                      </span>
                      <span className="mono small muted">
                        to {clock(item.ends_at)}
                      </span>
                    </div>
                    <div className="activity__info">
                      <h3
                        id={`item-${item.item_id}`}
                        className="activity__title"
                      >
                        {item.title}
                      </h3>
                      <div className="activity__meta">
                        <span>{item.location}</span>
                        <span>Est. {money(item.estimated_cost)}</span>
                        {provenance(byId.get(item.proposal_id)) && (
                          <span className="mono ok">
                            {provenance(byId.get(item.proposal_id))}
                          </span>
                        )}
                      </div>
                    </div>
                    {viewer.isOrganizer && (
                      <div className="activity__actions">
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => {
                            setCancelError(null);
                            setCancelling(item);
                          }}
                        >
                          Cancel activity
                        </button>
                      </div>
                    )}
                  </article>
                ))}
                {day.voting.map((p) => (
                  <Link
                    key={p.proposal_id}
                    to={`/trips/${trip.trip_id}#proposal-${p.proposal_id}`}
                    className="activity-pending"
                  >
                    <span>
                      <strong>{p.title}</strong> is still being voted on
                    </span>
                    {p.poll && (
                      <span className="mono">
                        CLOSES IN{' '}
                        {countdown(p.poll.deadline, now).toUpperCase()}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            </li>
          );
        })}
      </ol>

      {cancelling && (
        <ConfirmDialog
          title="Cancel this activity?"
          confirmLabel="Cancel activity"
          danger
          busy={cancel.isPending}
          error={cancelError}
          onConfirm={confirmCancel}
          onCancel={() => setCancelling(null)}
        >
          <p>
            <strong>{cancelling.title}</strong> will come off the itinerary for
            everyone. Its poll result stays in the proposal history.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
