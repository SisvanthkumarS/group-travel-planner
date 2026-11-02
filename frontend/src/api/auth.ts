import { apiRequest } from './client';
import type { LoginRequest, RegisterRequest, User } from './types';

// Register, login and logout are public routes on the backend; a 401 here
// means bad credentials, so they opt out of the global sign-out handler.

export const register = (body: RegisterRequest) =>
  apiRequest<User>('/auth/register', { method: 'POST', body, auth: false });

export const login = (body: LoginRequest) =>
  apiRequest<User>('/auth/login', { method: 'POST', body, auth: false });

export const logout = () =>
  apiRequest<void>('/auth/logout', { method: 'POST', auth: false });

/**
 * The signed-in user, from the session cookie. Not in the backend yet; the
 * session restore code falls back gracefully while it returns 404.
 * Called during startup, so it must not trigger the sign-out handler.
 */
export const getMe = () => apiRequest<User>('/auth/me', { auth: false });
