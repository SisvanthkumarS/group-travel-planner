import { ApiError } from '../api/client';

/**
 * Open trip pages and the trips list refresh this often, so changes other
 * members make (new proposals, votes, closed polls, cancellations, edits)
 * show up without a reload. Polling pauses while the browser tab is hidden.
 */
export const LIVE_REFRESH_MS = 10_000;

/** The trip was deleted (404) or the viewer was removed from it (403). */
export const tripIsGone = (error: unknown) =>
  error instanceof ApiError && (error.status === 403 || error.status === 404);
