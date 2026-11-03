import { useMemo, useState } from 'react';
import {
  Link,
  NavLink,
  Outlet,
  useNavigate,
  useParams,
} from 'react-router-dom';
import { ApiError } from '../../api/client';
import {
  useDeleteTrip,
  useItinerary,
  useProposals,
  useTrip,
} from '../../api/hooks';
import { useAuth } from '../../auth/AuthProvider';
import { Avatar, BackIcon, PlusIcon, QueryError } from '../../components/bits';
import { ConfirmDialog } from '../../components/Modal';
import { tripDates, zoneLabel } from '../../lib/format';
import type { TripContext } from './context';
import { InviteModal } from './InviteModal';

const MAX_TRAVELERS = 8;

function TripUnavailable({ error }: { error: unknown }) {
  const status = error instanceof ApiError ? error.status : 0;
  const message =
    status === 403
      ? "You're not a member of this trip."
      : status === 404
        ? 'This trip does not exist or was deleted.'
        : null;
  return (
    <main className="page">
      <Link to="/trips" className="back-link">
        <BackIcon /> All trips
      </Link>
      {message ? (
        <div className="empty">
          <p>{message}</p>
        </div>
      ) : (
        <QueryError error={error} />
      )}
    </main>
  );
}

/** Trip workspace frame: ticket header, organizer actions and tabs (US-11). */
export function TripLayout() {
  const tripId = Number(useParams().tripId);
  const { user } = useAuth();
  const navigate = useNavigate();
  const trip = useTrip(tripId);
  const proposals = useProposals(tripId);
  const itinerary = useItinerary(tripId);
  const deleteTrip = useDeleteTrip();
  const [inviting, setInviting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const context = useMemo<TripContext | null>(() => {
    if (!trip.data || !user) return null;
    const names = new Map(
      trip.data.members.map((m) => [m.user_id, m.user_name]),
    );
    const members = [...trip.data.members].sort(
      (a, b) => Number(b.role === 'ORGANIZER') - Number(a.role === 'ORGANIZER'),
    );
    return {
      trip: trip.data,
      members,
      viewer: {
        userId: user.user_id,
        isOrganizer: trip.data.organizer_id === user.user_id,
      },
      memberName: (id) =>
        id === user.user_id ? 'you' : (names.get(id) ?? 'a former member'),
    };
  }, [trip.data, user]);

  if (trip.error) return <TripUnavailable error={trip.error} />;
  if (!context) {
    return (
      <main className="page">
        <p className="muted" role="status">
          Loading trip…
        </p>
      </main>
    );
  }

  const { trip: t, viewer, members } = context;
  const organizerName = viewer.isOrganizer
    ? 'you'
    : context.memberName(t.organizer_id);

  async function handleDelete() {
    setDeleteError(null);
    try {
      await deleteTrip.mutateAsync(tripId);
      navigate('/trips', { replace: true });
    } catch (e) {
      setDeleteError(
        e instanceof Error ? e.message : 'Could not delete the trip.',
      );
    }
  }

  return (
    <main className="page page--trip">
      <Link to="/trips" className="back-link">
        <BackIcon /> All trips
      </Link>

      <section className="trip-ticket">
        <div className="trip-ticket__main">
          <span className="eyebrow eyebrow--dark">
            {t.destination.toUpperCase()}
          </span>
          <h1 className="trip-ticket__name">{t.name}</h1>
          <div className="trip-ticket__meta">
            <span className="mono trip-ticket__dates">
              {tripDates(t.start_date, t.end_date)}
            </span>
            <span title={t.timezone}>Times in {zoneLabel(t.timezone)}</span>
            <span>
              Organized by <strong>{organizerName}</strong>
            </span>
            <span
              className="avatar-stack"
              aria-label={`${members.length} travelers`}
            >
              {members.slice(0, 4).map((m) => (
                <Avatar key={m.user_id} name={m.user_name} userId={m.user_id} />
              ))}
              {members.length > 4 && (
                <span className="avatar avatar--more">
                  +{members.length - 4}
                </span>
              )}
            </span>
          </div>
        </div>
        {viewer.isOrganizer && (
          <div className="trip-ticket__stub">
            <button
              type="button"
              className="btn btn--light"
              onClick={() => setInviting(true)}
              disabled={members.length >= MAX_TRAVELERS}
            >
              <PlusIcon />
              {members.length >= MAX_TRAVELERS
                ? 'Trip is full'
                : 'Invite traveler'}
            </button>
            <button
              type="button"
              className="btn btn--ghost-danger"
              onClick={() => setConfirmDelete(true)}
            >
              Delete trip
            </button>
          </div>
        )}
      </section>

      <nav className="tabs" aria-label="Trip sections">
        <NavLink end to={`/trips/${tripId}`} className="tabs__tab">
          Proposals{' '}
          <span className="tabs__count">{proposals.data?.length ?? '–'}</span>
        </NavLink>
        <NavLink to={`/trips/${tripId}/itinerary`} className="tabs__tab">
          Itinerary{' '}
          <span className="tabs__count">{itinerary.data?.length ?? '–'}</span>
        </NavLink>
      </nav>

      <Outlet context={context} />

      {inviting && (
        <InviteModal
          trip={t}
          memberCount={members.length}
          onClose={() => setInviting(false)}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          title="Delete this trip?"
          confirmLabel="Delete trip"
          danger
          busy={deleteTrip.isPending}
          error={deleteError}
          onConfirm={handleDelete}
          onCancel={() => {
            setConfirmDelete(false);
            setDeleteError(null);
          }}
        >
          <p>
            <strong>{t.name}</strong> and all of its proposals, votes and
            itinerary will be removed for everyone. This can't be undone.
          </p>
        </ConfirmDialog>
      )}
    </main>
  );
}
