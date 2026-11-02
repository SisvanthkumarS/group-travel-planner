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
  it('uses GET /auth/me when the backend has it', async () => {
    const fetch = vi.fn().mockResolvedValue(json(user));
    vi.stubGlobal('fetch', fetch);

    await expect(restoreSession()).resolves.toEqual(user);
    expect(fetch.mock.calls[0][0]).toMatch(/\/auth\/me$/);
  });

  it('is signed out when /auth/me returns 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(json({ detail: 'x' }, 401)),
    );
    await expect(restoreSession()).resolves.toBeNull();
  });

  it('falls back to the cached user while /auth/me is missing', async () => {
    writeCachedUser(user);
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: 'Not Found' }, 404))
      .mockResolvedValueOnce(json([]));
    vi.stubGlobal('fetch', fetch);

    await expect(restoreSession()).resolves.toEqual(user);
    expect(fetch.mock.calls[1][0]).toMatch(/\/trips$/);
  });

  it('signs out and clears the cache when the cookie has expired', async () => {
    writeCachedUser(user);
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json({ detail: 'Not Found' }, 404))
        .mockResolvedValueOnce(
          json({ detail: 'Authentication required.' }, 401),
        ),
    );

    await expect(restoreSession()).resolves.toBeNull();
    expect(readCachedUser()).toBeNull();
  });

  it('is signed out with no cached user and no /auth/me', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ detail: 'Not Found' }, 404));
    vi.stubGlobal('fetch', fetch);

    await expect(restoreSession()).resolves.toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
  });
});
