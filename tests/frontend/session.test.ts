import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  initials,
  readCachedUser,
  registerConflictField,
  restoreSession,
  toLoginRequest,
  toRegisterRequest,
  validateRegister,
  validateSignIn,
  writeCachedUser,
} from '../../frontend/src/auth/session';

const user = {
  user_id: 7,
  user_name: 'sisvanth',
  email: 'sisvanth@nyu.edu',
  created_at: '2026-11-01T00:00:00Z',
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

// Minimal in-memory localStorage for the node test environment.
function stubStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    },
  });
}

beforeEach(stubStorage);
afterEach(() => vi.unstubAllGlobals());

describe('toLoginRequest (US-02)', () => {
  it('sends an identifier with @ as email', () => {
    expect(toLoginRequest(' sisvanth@nyu.edu ', 'pw')).toEqual({
      email: 'sisvanth@nyu.edu',
      password: 'pw',
    });
  });

  it('sends anything else as a username', () => {
    expect(toLoginRequest('sisvanth', 'pw')).toEqual({
      user_name: 'sisvanth',
      password: 'pw',
    });
  });
});

describe('validateSignIn', () => {
  it('requires both fields', () => {
    expect(validateSignIn({ identifier: ' ', password: '' })).toEqual({
      identifier: expect.any(String),
      password: expect.any(String),
    });
    expect(validateSignIn({ identifier: 'a', password: 'b' })).toEqual({});
  });
});

describe('validateRegister (US-01)', () => {
  const valid = {
    user_name: 'sisvanth',
    email: 'a@b.co',
    password: '12345678',
  };

  it('accepts a valid form', () => {
    expect(validateRegister(valid)).toEqual({});
  });

  it('rejects a password shorter than 8 characters', () => {
    expect(
      validateRegister({ ...valid, password: '1234567' }).password,
    ).toMatch(/8/);
  });

  it('rejects an invalid email and a blank or long username', () => {
    expect(validateRegister({ ...valid, email: 'nope' }).email).toBeDefined();
    expect(
      validateRegister({ ...valid, user_name: '  ' }).user_name,
    ).toBeDefined();
    expect(
      validateRegister({ ...valid, user_name: 'x'.repeat(31) }).user_name,
    ).toBeDefined();
  });

  it('trims the username and email before sending', () => {
    expect(
      toRegisterRequest({ user_name: ' s ', email: ' a@b.co ', password: 'p' }),
    ).toEqual({
      user_name: 's',
      email: 'a@b.co',
      password: 'p',
    });
  });
});

describe('registerConflictField', () => {
  it('maps backend 409 messages to the right field', () => {
    expect(registerConflictField('Email is already registered.')).toBe('email');
    expect(registerConflictField('Username is already registered.')).toBe(
      'user_name',
    );
    expect(registerConflictField('Something else')).toBeUndefined();
  });
});

describe('initials', () => {
  it('uses the first two letters or digits', () => {
    expect(initials('sisvanth')).toBe('SI');
    expect(initials('a.b')).toBe('AB');
    expect(initials('...')).toBe('?');
  });
});

describe('cached user', () => {
  it('round-trips and clears', () => {
    writeCachedUser(user);
    expect(readCachedUser()).toEqual(user);
    writeCachedUser(null);
    expect(readCachedUser()).toBeNull();
  });

  it('survives storage that throws', () => {
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => {
          throw new Error('blocked');
        },
        setItem: () => {
          throw new Error('blocked');
        },
      },
    });
    expect(() => writeCachedUser(user)).not.toThrow();
    expect(readCachedUser()).toBeNull();
  });
});

describe('restoreSession (US-02, US-03)', () => {
  it('confirms the cached user through the existing trips endpoint only', async () => {
    writeCachedUser(user);
    const fetch = vi.fn().mockResolvedValue(json([]));
    vi.stubGlobal('fetch', fetch);

    await expect(restoreSession()).resolves.toEqual(user);
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toMatch(/\/trips$/);
    expect(fetch.mock.calls[0][1]).toMatchObject({
      method: 'GET',
      credentials: 'include',
    });
  });

  it('signs out and clears the cache when the cookie has expired', async () => {
    writeCachedUser(user);
    const fetch = vi
      .fn()
      .mockResolvedValue(json({ detail: 'Authentication required.' }, 401));
    vi.stubGlobal('fetch', fetch);

    await expect(restoreSession()).resolves.toBeNull();
    expect(readCachedUser()).toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
  });

  it('makes no request when there is no cached user', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);

    await expect(restoreSession()).resolves.toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('preserves the cached user when the backend is temporarily unavailable', async () => {
    writeCachedUser(user);
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          json(
            { detail: 'Authentication service temporarily unavailable.' },
            503,
          ),
        ),
    );

    await expect(restoreSession()).rejects.toMatchObject({ status: 503 });
    expect(readCachedUser()).toEqual(user);
  });

  it('preserves the cached user on network failure', async () => {
    writeCachedUser(user);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Network failed')),
    );

    await expect(restoreSession()).rejects.toMatchObject({ status: 0 });
    expect(readCachedUser()).toEqual(user);
  });
});
