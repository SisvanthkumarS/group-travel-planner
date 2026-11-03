import { useState, type FormEvent } from 'react';
import { ApiError } from '../../api/client';
import { useCreateProposal } from '../../api/hooks';
import { Field } from '../../components/Field';
import { Modal } from '../../components/Modal';
import {
  fromDateTimeLocal,
  instantOf,
  parseDateOnly,
  shortDate,
  tripDates,
  zoneLabel,
} from '../../lib/format';
import { useTripContext } from './context';

export type ProposalFields = {
  title: string;
  location: string;
  starts_at: string; // datetime-local value
  ends_at: string;
  estimated_cost: string;
  description: string;
};
type Errors = Partial<Record<keyof ProposalFields, string>>;

/**
 * Mirrors the backend rules so most mistakes are caught before sending (US-07).
 * Times are entered on the trip's clock, so the date part of the input is
 * already the trip-local day.
 */
export function validateProposal(
  f: ProposalFields,
  trip: { start_date: string; end_date: string; timezone: string },
  now: number = Date.now(),
): Errors {
  const errors: Errors = {};
  if (!f.title.trim()) errors.title = 'Give the activity a name.';
  if (!f.location.trim()) errors.location = 'Where is it?';
  if (!f.description.trim())
    errors.description = 'Add a sentence on why the group should go.';

  const cost = Number(f.estimated_cost);
  if (f.estimated_cost.trim() === '' || !Number.isFinite(cost))
    errors.estimated_cost = 'Enter a cost, or 0 if free.';
  else if (cost < 0) errors.estimated_cost = "Cost can't be negative.";

  const range = `Must fall within the trip dates, ${shortDate(parseDateOnly(trip.start_date))} to ${shortDate(parseDateOnly(trip.end_date))}.`;
  const inTrip = (v: string) => {
    const day = v.slice(0, 10);
    return day >= trip.start_date && day <= trip.end_date;
  };
  const at = (v: string) => instantOf(v, trip.timezone);

  if (!f.starts_at) errors.starts_at = 'Pick a start time.';
  else if (at(f.starts_at) <= now) errors.starts_at = 'Must be in the future.';
  else if (!inTrip(f.starts_at)) errors.starts_at = range;

  if (!f.ends_at) errors.ends_at = 'Pick an end time.';
  else if (f.starts_at && at(f.ends_at) <= at(f.starts_at))
    errors.ends_at = 'Must be after the start.';
  else if (!inTrip(f.ends_at)) errors.ends_at = range;

  return errors;
}

export function NewProposalModal({ onClose }: { onClose: () => void }) {
  const { trip } = useTripContext();
  const create = useCreateProposal(trip.trip_id);
  const [fields, setFields] = useState<ProposalFields>({
    title: '',
    location: '',
    starts_at: '',
    ends_at: '',
    estimated_cost: '0',
    description: '',
  });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);

  const set =
    (key: keyof ProposalFields) => (e: { target: { value: string } }) =>
      setFields((f) => ({ ...f, [key]: e.target.value }));

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateProposal(fields, trip);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length) return;
    try {
      await create.mutateAsync({
        title: fields.title.trim(),
        location: fields.location.trim(),
        description: fields.description.trim(),
        estimated_cost: Number(fields.estimated_cost),
        starts_at: fromDateTimeLocal(fields.starts_at, trip.timezone),
        ends_at: fromDateTimeLocal(fields.ends_at, trip.timezone),
      });
      onClose();
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status === 422 &&
        Object.keys(e.fieldErrors).length
      ) {
        setErrors(e.fieldErrors as Errors);
      } else {
        setFormError(
          e instanceof Error ? e.message : 'Could not submit the proposal.',
        );
      }
    }
  }

  return (
    <Modal
      title="New proposal"
      size="lg"
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
        {formError && (
          <div className="form-error" role="alert">
            {formError}
          </div>
        )}
        <Field
          label="Activity"
          value={fields.title}
          onChange={set('title')}
          error={errors.title}
        />
        <Field
          label="Location"
          value={fields.location}
          onChange={set('location')}
          error={errors.location}
        />
        <div className="grid-2">
          <Field
            label="Starts"
            type="datetime-local"
            className="field__input field__input--mono"
            min={`${trip.start_date}T00:00`}
            max={`${trip.end_date}T23:59`}
            value={fields.starts_at}
            onChange={set('starts_at')}
            error={errors.starts_at}
            hint={`In ${zoneLabel(trip.timezone)}.`}
          />
          <Field
            label="Ends"
            type="datetime-local"
            className="field__input field__input--mono"
            min={fields.starts_at || `${trip.start_date}T00:00`}
            max={`${trip.end_date}T23:59`}
            value={fields.ends_at}
            onChange={set('ends_at')}
            error={errors.ends_at}
          />
        </div>
        <div className="field field--narrow">
          <label htmlFor="proposal-cost" className="field__label">
            Estimated cost per person
          </label>
          <div
            className="money-input"
            data-invalid={errors.estimated_cost ? true : undefined}
          >
            <span className="money-input__prefix mono" aria-hidden="true">
              $
            </span>
            <input
              id="proposal-cost"
              type="number"
              min="0"
              step="1"
              inputMode="decimal"
              className="money-input__field mono"
              value={fields.estimated_cost}
              onChange={set('estimated_cost')}
              aria-invalid={errors.estimated_cost ? true : undefined}
              aria-describedby={
                errors.estimated_cost ? 'proposal-cost-error' : undefined
              }
            />
          </div>
          {errors.estimated_cost && (
            <span id="proposal-cost-error" className="field__error">
              {errors.estimated_cost}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="proposal-desc" className="field__label">
            Why go?
          </label>
          <textarea
            id="proposal-desc"
            rows={4}
            className="field__input field__textarea"
            value={fields.description}
            onChange={set('description')}
            aria-invalid={errors.description ? true : undefined}
            aria-describedby={
              errors.description ? 'proposal-desc-error' : undefined
            }
          />
          {errors.description && (
            <span id="proposal-desc-error" className="field__error">
              {errors.description}
            </span>
          )}
        </div>
        <div className="notice">
          It starts as <strong>Pending</strong>. The organizer opens a poll, and
          if the group votes yes it goes on the itinerary.
        </div>
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
            disabled={create.isPending}
          >
            {create.isPending ? 'Submitting…' : 'Submit proposal'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
