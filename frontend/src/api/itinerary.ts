import { apiRequest } from './client';
import type { ItineraryItem } from './types';

/** Active approved activities, in chronological order. */
export const getItinerary = (tripId: number) =>
  apiRequest<ItineraryItem[]>(`/trips/${tripId}/itinerary`);

/** Organizer only. Marks the activity CANCELLED; poll history is kept. */
export const cancelItineraryItem = (tripId: number, itemId: number) =>
  apiRequest<void>(`/trips/${tripId}/itinerary/${itemId}`, {
    method: 'DELETE',
  });
