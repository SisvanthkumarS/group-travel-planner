import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './client';

/** Retrying a 4xx never helps: the request itself is wrong or forbidden. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
    return false;
  }
  return failureCount < 2;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        staleTime: 10_000,
        refetchOnWindowFocus: true,
      },
      mutations: { retry: false },
    },
  });
}

// Keys are nested under the trip so invalidating ['trips', id] refreshes
// that trip's details, proposals and itinerary together.
export const queryKeys = {
  trips: ['trips'] as const,
  trip: (tripId: number) => ['trips', tripId] as const,
  proposals: (tripId: number) => ['trips', tripId, 'proposals'] as const,
  itinerary: (tripId: number) => ['trips', tripId, 'itinerary'] as const,
  invitations: ['invitations'] as const,
};
