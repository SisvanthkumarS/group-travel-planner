import { apiRequest } from './client';
import type {
  CreateTripRequest,
  Trip,
  TripDetail,
  UpdateTripRequest,
} from './types';

export const listTrips = () => apiRequest<Trip[]>('/trips');

export const createTrip = (body: CreateTripRequest) =>
  apiRequest<Trip>('/trips', { method: 'POST', body });

export const getTrip = (tripId: number) =>
  apiRequest<TripDetail>(`/trips/${tripId}`);

/** US-18: send only the fields that changed; the rest stay as they are. */
export const updateTrip = (tripId: number, body: UpdateTripRequest) =>
  apiRequest<Trip>(`/trips/${tripId}`, { method: 'PATCH', body });

export const deleteTrip = (tripId: number) =>
  apiRequest<void>(`/trips/${tripId}`, { method: 'DELETE' });
