import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useInvitations, useRespondToInvitation, useTrips } from '../api/hooks';
import type { Invitation, Trip } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { PlusIcon, QueryError, RoleChip } from '../components/bits';
import { tripDates } from '../lib/format';
import { CreateTripModal } from './CreateTripModal';

/**
 * The backend currently returns invitations with IDs only. These optional
 * fields are what the team agreed to add for US-06; the UI uses them when
 * present and falls back otherwise.
 */
type InvitationView = Invitation & {
  trip_name?: string;
  destination?: string;
  start_date?: string;
  end_date?: string;
  invited_by_user_name?: string;
};

function InvitationRow({ invitation }: { invitation: InvitationView }) {
  const respond = useRespondToInvitation();
  const [error, setError] = useState<string | null>(null);

  async function answer(decision: 'ACCEPT' | 'DECLINE') {
    setError(null);
    try {
      await respond.mutateAsync({
        invitation_id: invitation.invitation_id,
        decision,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not respond.');
    }
  }

  const when =
    invitation.start_date && invitation.end_date
      ? tripDates(invitation.start_date, invitation.end_date)
      : null;

  return (
    <li className="invite-row">
      <div className="invite-row__text">
        <span className="invite-row__title">
          {invitation.trip_name ?? 'Trip invitation'}
        </span>
        <span className="invite-row__meta">
          {invitation.invited_by_user_name ? (
            <>
              Invited by <strong>{invitation.invited_by_user_name}</strong>
            </>
          ) : (
            'You were invited to plan a trip'
          )}
          {when && (
            <>
              {' · '}
              <span className="mono">{when}</span>
            </>
          )}
        </span>
        {error && (
          <span className="field__error" role="alert">
            {error}
          </span>
        )}
      </div>
      <div className="invite-row__actions">
        <button
          type="button"
          className="btn btn--secondary btn--md"
          onClick={() => answer('DECLINE')}
          disabled={respond.isPending}
        >
          Decline
        </button>
        <button
          type="button"
          className="btn btn--ink btn--md"
          onClick={() => answer('ACCEPT')}
          disabled={respond.isPending}
        >
          Accept
        </button>
      </div>
    </li>
  );
}

function Invitations() {
  const { data, error, refetch } = useInvitations();
  if (error) return <QueryError error={error} onRetry={() => refetch()} />;
  const pending = (data ?? []).filter(
    (i) => i.status === 'PENDING',
  ) as InvitationView[];
  if (pending.length === 0) return null;

  return (
    <section
      id="invitations"
      className="invitations"
      aria-labelledby="invitations-title"
    >
      <h2 id="invitations-title" className="invitations__title">
        {pending.length === 1
          ? '1 invitation'
          : `${pending.length} invitations`}{' '}
        waiting for you
      </h2>
      <ul className="invitations__list">
        {pending.map((inv) => (
          <InvitationRow key={inv.invitation_id} invitation={inv} />
        ))}
      </ul>
    </section>
  );
}

function TripCard({ trip, organizer }: { trip: Trip; organizer: boolean }) {
  return (
    <Link to={`/trips/${trip.trip_id}`} className="trip-card">
      <div className="trip-card__main">
        <div className="trip-card__top">
          <span className="eyebrow">{trip.destination.toUpperCase()}</span>
          <RoleChip organizer={organizer} />
        </div>
        <span className="trip-card__name">{trip.name}</span>
        <span className="mono trip-card__dates">
          {tripDates(trip.start_date, trip.end_date)}
        </span>
      </div>
      <div className="trip-card__stub">Open trip</div>
    </Link>
  );
}

export function TripsPage() {
  const { user } = useAuth();
  const trips = useTrips();
  const [creating, setCreating] = useState(false);

  return (
    <main className="page">
      <div className="page__header page__header--row">
        <div>
          <h1 className="page__title">Your trips</h1>
          <p className="page__subtitle">Trips you organize or have joined.</p>
        </div>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => setCreating(true)}
        >
          <PlusIcon />
          New trip
        </button>
      </div>

      <Invitations />

      {trips.error ? (
        <QueryError error={trips.error} onRetry={() => trips.refetch()} />
      ) : trips.isPending ? (
        <p className="muted" role="status">
          Loading trips…
        </p>
      ) : trips.data.length === 0 ? (
        <div className="empty">
          <p>
            No trips yet. Create one, or accept an invitation from a friend.
          </p>
        </div>
      ) : (
        <section className="trip-grid" aria-label="Trips">
          {trips.data.map((trip) => (
            <TripCard
              key={trip.trip_id}
              trip={trip}
              organizer={trip.organizer_id === user?.user_id}
            />
          ))}
        </section>
      )}

      {creating && <CreateTripModal onClose={() => setCreating(false)} />}
    </main>
  );
}
