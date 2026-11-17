import { useState, type FormEvent } from 'react';
import { ApiError } from '../../api/client';
import { useUpdateTrip } from '../../api/hooks';
import type { TripDetail } from '../../api/types';
import { Modal } from '../../components/Modal';
import {
  movesTripCalendar,
  tripChanges,
  tripFormValues,
} from '../../lib/trips';
import {
  applyTripError,
  TripFields,
  validateTrip,
  type TripFormErrors,
  type TripFormFields,
} from '../CreateTripModal';

/** US-18: the organizer edits the trip; fields left as they were are not sent. */
export function EditTripModal({
  trip,
  onClose,
}: {
  trip: TripDetail;
  onClose: () => void;
}) {
  const updateTrip = useUpdateTrip(trip.trip_id);
  const [fields, setFields] = useState<TripFormFields>(() =>
    tripFormValues(trip),
  );
  const [errors, setErrors] = useState<TripFormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  const changes = tripChanges(trip, fields);
  const unchanged = Object.keys(changes).length === 0;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateTrip(fields);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length) return;
    if (unchanged) {
      onClose();
      return;
    }
    try {
      await updateTrip.mutateAsync(changes);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setFormError('Only the organizer can edit this trip.');
      } else if (error instanceof ApiError && error.status === 404) {
        setFormError('This trip no longer exists.');
      } else {
        applyTripError(
          error,
          setErrors,
          setFormError,
          'Could not save the trip.',
        );
      }
    }
  }

  return (
    <Modal
      title="Edit trip"
      subtitle="Changes show for everyone in the trip."
      onClose={onClose}
    >
      <form className="stack" onSubmit={handleSubmit} noValidate>
        {formError && (
          <div className="form-error" role="alert">
            {formError}
          </div>
        )}
        <TripFields
          fields={fields}
          errors={errors}
          onChange={(key, value) => {
            setFields((f) => ({ ...f, [key]: value }));
            setErrors((e) => ({ ...e, [key]: undefined }));
          }}
        />
        {movesTripCalendar(changes) && (
          <p className="small muted" role="note">
            Proposals and itinerary activities keep their exact times. Anything
            that falls outside the new dates still shows on its own day.
          </p>
        )}
        <div className="actions">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={updateTrip.isPending || unchanged}
          >
            {updateTrip.isPending ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
