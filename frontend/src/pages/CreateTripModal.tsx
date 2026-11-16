import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useCreateTrip } from '../api/hooks';
import type { CreateTripRequest } from '../api/types';
import { Field } from '../components/Field';
import { Modal } from '../components/Modal';
import { viewerTimeZone, zoneLabel } from '../lib/format';

export type TripFormFields = CreateTripRequest;
export type TripFormErrors = Partial<Record<keyof TripFormFields, string>>;

export function validateTrip(f: TripFormFields): TripFormErrors {
  const errors: TripFormErrors = {};
  if (!f.name.trim()) errors.name = 'Give the trip a name.';
  if (!f.destination.trim()) errors.destination = 'Add a destination.';
  if (!f.start_date) errors.start_date = 'Pick a start date.';
  if (!f.end_date) errors.end_date = 'Pick an end date.';
  else if (f.start_date && f.end_date < f.start_date)
    errors.end_date = "End date can't be before the start date.";
  if (!f.timezone.trim())
    errors.timezone = 'Pick the time zone the trip is in.';
  return errors;
}

/** Every IANA zone the browser knows, with the trip's own zone guaranteed. */
function timeZoneOptions(current: string): string[] {
  const zones = Intl.supportedValuesOf('timeZone');
  return zones.includes(current) ? zones : [current, ...zones];
}

/** The trip's name, destination, dates and time zone; shared by create and edit. */
export function TripFields({
  fields,
  errors,
  onChange,
}: {
  fields: TripFormFields;
  errors: TripFormErrors;
  onChange: (key: keyof TripFormFields, value: string) => void;
}) {
  const set =
    (key: keyof TripFormFields) => (e: { target: { value: string } }) =>
      onChange(key, e.target.value);
  return (
    <>
      <Field
        label="Trip name"
        value={fields.name}
        onChange={set('name')}
        error={errors.name}
      />
      <Field
        label="Destination"
        value={fields.destination}
        onChange={set('destination')}
        error={errors.destination}
        hint="One destination per trip."
      />
      <div className="grid-2">
        <Field
          label="Start date"
          type="date"
          className="field__input field__input--mono"
          value={fields.start_date}
          onChange={set('start_date')}
          error={errors.start_date}
        />
        <Field
          label="End date"
          type="date"
          className="field__input field__input--mono"
          min={fields.start_date || undefined}
          value={fields.end_date}
          onChange={set('end_date')}
          error={errors.end_date}
        />
      </div>
      <div className="field">
        <label htmlFor="trip-timezone" className="field__label">
          Time zone
        </label>
        <select
          id="trip-timezone"
          className="field__input"
          value={fields.timezone}
          onChange={set('timezone')}
          aria-invalid={errors.timezone ? true : undefined}
          aria-describedby="trip-timezone-message"
        >
          {timeZoneOptions(fields.timezone).map((zone) => (
            <option key={zone} value={zone}>
              {zone.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        {errors.timezone ? (
          <span id="trip-timezone-message" className="field__error">
            {errors.timezone}
          </span>
        ) : (
          <span id="trip-timezone-message" className="field__hint">
            Where the trip happens. Activity times show in{' '}
            {zoneLabel(fields.timezone)} for everyone.
          </span>
        )}
      </div>
    </>
  );
}

/** Puts a 422 from the API on the matching fields, or on the form if none match. */
export function applyTripError(
  error: unknown,
  setErrors: (errors: TripFormErrors) => void,
  setFormError: (message: string) => void,
  fallback: string,
) {
  if (error instanceof ApiError && error.status === 422) {
    setErrors(error.fieldErrors as TripFormErrors);
    if (!Object.keys(error.fieldErrors).length) setFormError(error.message);
  } else {
    setFormError(error instanceof Error ? error.message : fallback);
  }
}

/** US-04: create a trip; the creator becomes its organizer. */
export function CreateTripModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const createTrip = useCreateTrip();
  const [fields, setFields] = useState<TripFormFields>({
    name: '',
    destination: '',
    start_date: '',
    end_date: '',
    timezone: viewerTimeZone(),
  });
  const [errors, setErrors] = useState<TripFormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateTrip(fields);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length) return;
    try {
      const trip = await createTrip.mutateAsync({
        ...fields,
        name: fields.name.trim(),
        destination: fields.destination.trim(),
        timezone: fields.timezone.trim(),
      });
      navigate(`/trips/${trip.trip_id}`);
    } catch (error) {
      applyTripError(
        error,
        setErrors,
        setFormError,
        'Could not create the trip.',
      );
    }
  }

  return (
    <Modal
      title="New trip"
      subtitle="You'll be the organizer. Invite people once it's created."
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
            disabled={createTrip.isPending}
          >
            {createTrip.isPending ? 'Creating…' : 'Create trip'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
