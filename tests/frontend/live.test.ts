import { describe, expect, it } from 'vitest';
import { ApiError } from '../../frontend/src/api/client';
import { LIVE_REFRESH_MS, tripIsGone } from '../../frontend/src/lib/live';

describe('live refresh', () => {
  it('refreshes open pages every 10 seconds', () => {
    expect(LIVE_REFRESH_MS).toBe(10_000);
  });

  it('treats a deleted trip or lost access as gone, not as a blip', () => {
    expect(tripIsGone(new ApiError(404, 'Not found'))).toBe(true);
    expect(tripIsGone(new ApiError(403, 'Forbidden'))).toBe(true);
    expect(tripIsGone(new ApiError(500, 'Server error'))).toBe(false);
    expect(tripIsGone(new Error('offline'))).toBe(false);
  });
});
