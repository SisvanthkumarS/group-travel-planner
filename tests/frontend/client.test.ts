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
      method: 'GET',
      credentials: 'include',
      headers: new Headers({ Authorization: 'Bearer test-token' }),
    },
  );
});
it.each(['POST', 'PUT', 'PATCH', 'DELETE'])(
  'sends cookies and CSRF protection for %s requests',
  async (method) => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetch);
    await expect(
      apiRequest('/auth/logout', undefined, {
        method: method.toLowerCase(),
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      }),
    ).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith(expect.any(String), {
      method,
      credentials: 'include',
      headers: new Headers({
        'Content-Type': 'application/json',
        'X-CSRF-Protection': '1',
      }),
      body: '{}',
    });
  },
);
it('rejects unsuccessful responses', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
  );
  await expect(apiRequest('/health')).rejects.toThrow('401');
});
