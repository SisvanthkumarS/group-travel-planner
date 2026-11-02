import { apiRequest } from './client';
import type { CreateTripRequest, Trip, TripDetail } from './types';

export const listTrips = () => apiRequest<Trip[]>('/trips');

export const createTrip = (body: CreateTripRequest) =>
  apiRequest<Trip>('/trips', { method: 'POST', body });

export const getTrip = (tripId: number) =>
  apiRequest<TripDetail>(`/trips/${tripId}`);

export const deleteTrip = (tripId: number) =>
  apiRequest<void>(`/trips/${tripId}`, { method: 'DELETE' });
