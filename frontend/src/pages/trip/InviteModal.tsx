import { useState, type FormEvent } from 'react';
import { ApiError } from '../../api/client';
import { useInvite } from '../../api/hooks';
import type { TripDetail } from '../../api/types';
import { CheckIcon } from '../../components/bits';
import { Modal } from '../../components/Modal';
import { tripDates } from '../../lib/format';

const MAX_TRAVELERS = 8;

/** US-05: organizer invites a registered user by email or username. */
export function InviteModal({
  trip,
  memberCount,
  onClose,
}: {
  trip: TripDetail;
  memberCount: number;
  onClose: () => void;
}) {
  const invite = useInvite(trip.trip_id);
  const [who, setWho] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const left = MAX_TRAVELERS - memberCount;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = who.trim();
    setError(null);
    setSentTo(null);
    if (!value) {
      setError('Enter their email or username.');
      return;
    }
    try {
      await invite.mutateAsync(
        value.includes('@') ? { email: value } : { user_name: value },
      );
      setSentTo(value);
      setWho('');
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setError(
          'No account uses that yet. Ask them to register first, then invite them.',
        );
      } else if (
        e instanceof ApiError &&
        e.status === 422 &&
        e.fieldErrors.email
      ) {
        setError("That doesn't look like a valid email.");
      } else {
        setError(e instanceof Error ? e.message : 'Could not send the invite.');
      }
    }
  }

  return (
    <Modal
      title="Invite a traveler"
      subtitle={
        <>
          {trip.name} ·{' '}
          <span className="mono">
            {tripDates(trip.start_date, trip.end_date)}
          </span>
        </>
      }
      onClose={onClose}
    >
      <form className="stack" onSubmit={handleSubmit} noValidate>
        <div className="seats">
          <div className="seats__label">
            <span>Seats</span>
            <span className="mono">
              {memberCount} OF {MAX_TRAVELERS} · {left} LEFT
            </span>
          </div>
          <div
            className="seats__row"
            role="img"
            aria-label={`${memberCount} of ${MAX_TRAVELERS} seats taken`}
          >
            {Array.from({ length: MAX_TRAVELERS }, (_, i) => (
              <span
                key={i}
                className={i < memberCount ? 'seat seat--taken' : 'seat'}
              />
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="invite-who" className="field__label">
            Email or username
          </label>
          <div className="inline-form">
            <input
              id="invite-who"
              className="field__input"
              value={who}
              onChange={(e) => setWho(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'invite-error' : undefined}
              autoComplete="off"
            />
            <button
              type="submit"
              className="btn btn--primary"
              disabled={invite.isPending || left <= 0}
            >
              {invite.isPending ? 'Sending…' : 'Send invite'}
            </button>
          </div>
          {error && (
            <span id="invite-error" className="field__error" role="alert">
              {error}
            </span>
          )}
        </div>

        {sentTo && (
          <div className="notice notice--ok" role="status">
            <CheckIcon size={18} />
            <span>
              Invite sent to <strong>{sentTo}</strong>. They'll see it on their
              trips page.
            </span>
          </div>
        )}

        <p className="muted small">
          Only people with an account can be invited. They join once they
          accept, and the trip stops at {MAX_TRAVELERS} travelers.
        </p>
      </form>
    </Modal>
  );
}
