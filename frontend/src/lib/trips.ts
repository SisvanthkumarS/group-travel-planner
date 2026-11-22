import type { CreateTripRequest, Trip, UpdateTripRequest } from '../api/types';

type EditableTrip = Pick<
  Trip,
  'name' | 'destination' | 'start_date' | 'end_date' | 'timezone'
>;

const EDITABLE = [
  'name',
  'destination',
  'start_date',
  'end_date',
  'timezone',
] as const;

/** The form starts from the trip as it is now. */
export function tripFormValues(trip: EditableTrip): CreateTripRequest {
  const { name, destination, start_date, end_date, timezone } = trip;
  return { name, destination, start_date, end_date, timezone };
}

/**
 * US-18: only the fields the organizer actually changed, trimmed. The backend
 * keeps every omitted field as it is, so an untouched form sends nothing.
 */
export function tripChanges(
  trip: EditableTrip,
  fields: CreateTripRequest,
): UpdateTripRequest {
  const changes: UpdateTripRequest = {};
  for (const key of EDITABLE) {
    const value = fields[key].trim();
    if (value !== trip[key]) changes[key] = value;
  }
  return changes;
}

/** Dates or time zone changed: existing activities keep their exact times. */
export function movesTripCalendar(changes: UpdateTripRequest): boolean {
  return (
    changes.start_date !== undefined ||
    changes.end_date !== undefined ||
    changes.timezone !== undefined
  );
}
