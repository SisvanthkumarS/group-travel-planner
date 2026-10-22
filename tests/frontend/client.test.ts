import { afterEach, expect, it, vi } from 'vitest';
import { apiRequest } from '../../frontend/src/api/client';

afterEach(() => vi.unstubAllGlobals());
it('passes a bearer token and decodes a successful response', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
  vi.stubGlobal('fetch', fetch);
  await expect(apiRequest('/health', 'test-token')).resolves.toEqual({
    status: 'ok',
  });
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/v1/health'),
    {
      headers: { Authorization: 'Bearer test-token' },
    },
  );
});
it('rejects unsuccessful responses', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
  );
  await expect(apiRequest('/health')).rejects.toThrow('401');
});
