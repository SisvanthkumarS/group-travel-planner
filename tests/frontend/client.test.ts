import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  apiRequest,
  onUnauthorized,
} from '../../frontend/src/api/client';
import { shouldRetry } from '../../frontend/src/api/queryClient';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

function stubFetch(response: Response | Error) {
  const fetch =
    response instanceof Error
      ? vi.fn().mockRejectedValue(response)
      : vi.fn().mockResolvedValue(response);
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    return error as ApiError;
  }
  throw new Error('expected the request to fail');
}

afterEach(() => vi.unstubAllGlobals());

describe('apiRequest', () => {
  it('sends the session cookie and decodes JSON', async () => {
    const fetch = stubFetch(json([{ trip_id: 1 }]));

    await expect(apiRequest('/trips')).resolves.toEqual([{ trip_id: 1 }]);

    const [url, init] = fetch.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/trips$/);
    expect(init).toMatchObject({ method: 'GET', credentials: 'include' });
    expect(init.headers).toBeUndefined();
  });

  it('serializes a JSON body', async () => {
    const fetch = stubFetch(json({ trip_id: 7 }, 201));

    await apiRequest('/trips', { method: 'POST', body: { name: 'Lisbon' } });

    const [, init] = fetch.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({
      'Content-Type': 'application/json',
      'X-CSRF-Protection': '1',
    });
    expect(init.body).toBe('{"name":"Lisbon"}');
  });

  it('returns undefined for 204 No Content', async () => {
    stubFetch(new Response(null, { status: 204 }));

    await expect(
      apiRequest('/trips/1', { method: 'DELETE' }),
    ).resolves.toBeUndefined();
  });

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'] as const)(
    'sends CSRF protection for %s requests without a body',
    async (method) => {
      const fetch = stubFetch(new Response(null, { status: 204 }));
      await apiRequest('/trips/1', { method });
      expect(fetch.mock.calls[0][1]).toMatchObject({
        method,
        credentials: 'include',
        headers: { 'X-CSRF-Protection': '1' },
      });
    },
  );

  it.each(['register', 'login', 'logout'])(
    'protects the public %s endpoint',
    async (action) => {
      const fetch = stubFetch(new Response(null, { status: 204 }));
      await apiRequest(`/auth/${action}`, { method: 'POST', auth: false });
      expect(fetch.mock.calls[0][1].headers).toEqual({
        'X-CSRF-Protection': '1',
      });
    },
  );

  it('uses the FastAPI detail string as the error message', async () => {
    stubFetch(json({ detail: 'Only the Trip Organizer can do that.' }, 403));

    const error = await caught(apiRequest('/trips/1', { method: 'DELETE' }));

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(403);
    expect(error.message).toBe('Only the Trip Organizer can do that.');
  });

  it('maps 422 validation errors to fields', async () => {
    stubFetch(
      json(
        {
          detail: [
            { loc: ['body', 'name'], msg: 'Field required' },
            {
              loc: ['body'],
              msg: 'Value error, start_date must be on or before end_date.',
            },
          ],
        },
        422,
      ),
    );

    const error = await caught(apiRequest('/trips', { method: 'POST' }));

    expect(error.status).toBe(422);
    expect(error.fieldErrors).toEqual({ name: 'Field required' });
    expect(error.message).toBe('start_date must be on or before end_date.');
  });

  it('falls back to the status code when the body is not JSON', async () => {
    stubFetch(new Response('Bad Gateway', { status: 502 }));

    const error = await caught(apiRequest('/trips'));

    expect(error.status).toBe(502);
    expect(error.message).toBe('Request failed (502)');
  });

  it('reports network failures as status 0', async () => {
    stubFetch(new TypeError('Failed to fetch'));

    const error = await caught(apiRequest('/trips'));

    expect(error.status).toBe(0);
    expect(error.message).toMatch(/could not reach the server/i);
  });
});

describe('onUnauthorized', () => {
  it('fires on a 401 from an authenticated request', async () => {
    const handler = vi.fn();
    const unsubscribe = onUnauthorized(handler);
    stubFetch(json({ detail: 'Authentication required.' }, 401));

    await caught(apiRequest('/trips'));

    expect(handler).toHaveBeenCalledOnce();
    unsubscribe();
  });

  it('does not fire for public endpoints like login', async () => {
    const handler = vi.fn();
    const unsubscribe = onUnauthorized(handler);
    stubFetch(json({ detail: 'Invalid login credentials.' }, 401));

    const error = await caught(
      apiRequest('/auth/login', { method: 'POST', auth: false }),
    );

    expect(error.status).toBe(401);
    expect(handler).not.toHaveBeenCalled();
    unsubscribe();
  });
});

describe('shouldRetry', () => {
  it('never retries client errors', () => {
    expect(shouldRetry(0, new ApiError(403, 'Forbidden'))).toBe(false);
    expect(shouldRetry(0, new ApiError(404, 'Not found'))).toBe(false);
  });

  it('retries server and network errors up to twice', () => {
    expect(shouldRetry(0, new ApiError(500, 'Oops'))).toBe(true);
    expect(shouldRetry(1, new ApiError(0, 'Offline'))).toBe(true);
    expect(shouldRetry(2, new ApiError(503, 'Down'))).toBe(false);
  });
});
