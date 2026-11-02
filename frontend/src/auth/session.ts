// Session helpers kept free of React so they are easy to unit test.
import { getMe } from '../api/auth';
import { ApiError, apiRequest } from '../api/client';
import type { LoginRequest, RegisterRequest, User } from '../api/types';

export const MIN_PASSWORD_LENGTH = 8;
export const MAX_USERNAME_LENGTH = 30;

const USER_KEY = 'gtp.user';

/** Cross-tab channel: a sign-out in one tab clears every other tab (US-03). */
export const AUTH_CHANNEL = 'gtp-auth';
export type AuthMessage =
  { type: 'signed-out' } | { type: 'signed-in'; user: User };

// Login accepts an email or a username; anything with an @ is treated as email.
export function toLoginRequest(
  identifier: string,
  password: string,
): LoginRequest {
  const id = identifier.trim();
  return id.includes('@')
    ? { email: id, password }
    : { user_name: id, password };
}

export type SignInFields = { identifier: string; password: string };
export type RegisterFields = {
  user_name: string;
  email: string;
  password: string;
};
export type FieldErrors<T> = Partial<Record<keyof T, string>>;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateSignIn(
  fields: SignInFields,
): FieldErrors<SignInFields> {
  const errors: FieldErrors<SignInFields> = {};
  if (!fields.identifier.trim())
    errors.identifier = 'Enter your email or username.';
  if (!fields.password) errors.password = 'Enter your password.';
  return errors;
}

export function validateRegister(
  fields: RegisterFields,
): FieldErrors<RegisterFields> {
  const errors: FieldErrors<RegisterFields> = {};
  const name = fields.user_name.trim();
  if (!name) errors.user_name = 'Choose a username.';
  else if (name.length > MAX_USERNAME_LENGTH)
    errors.user_name = `Use ${MAX_USERNAME_LENGTH} characters or fewer.`;
  if (!EMAIL_PATTERN.test(fields.email.trim()))
    errors.email = 'Enter a valid email address.';
  if (fields.password.length < MIN_PASSWORD_LENGTH)
    errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  return errors;
}

export function toRegisterRequest(fields: RegisterFields): RegisterRequest {
  return {
    user_name: fields.user_name.trim(),
    email: fields.email.trim(),
    password: fields.password,
  };
}

/** Which form field a 409 from POST /auth/register belongs to. */
export function registerConflictField(
  message: string,
): keyof RegisterFields | undefined {
  if (/email/i.test(message)) return 'email';
  if (/username/i.test(message)) return 'user_name';
  return undefined;
}

export function initials(userName: string): string {
  const letters = userName.replace(/[^\p{L}\p{N}]/gu, '');
  return (letters.slice(0, 2) || '?').toUpperCase();
}

// The cached user is display data only (id, name, email), never the token,
// which stays in the HttpOnly cookie. Storage can be unavailable (private
// mode, blocked site data), so every access is guarded.

export function readCachedUser(): User | null {
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function writeCachedUser(user: User | null): void {
  try {
    if (user) window.localStorage.setItem(USER_KEY, JSON.stringify(user));
    else window.localStorage.removeItem(USER_KEY);
  } catch {
    // Not fatal: the session still works for this page load.
  }
}

/**
 * Work out who is signed in when the app loads (US-02: stay signed in on
 * refresh). Returns null when there is no valid session.
 *
 * Prefers GET /auth/me. Until the backend ships it (it currently 404s), falls
 * back to the cached user, confirmed by an authenticated request so an
 * expired cookie still signs the user out.
 */
export async function restoreSession(): Promise<User | null> {
  try {
    return await getMe();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) return null;
    if (error.status !== 404) throw error;
  }

  const cached = readCachedUser();
  if (!cached) return null;
  try {
    await apiRequest('/trips', { auth: false });
    return cached;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      writeCachedUser(null);
      return null;
    }
    throw error;
  }
}
