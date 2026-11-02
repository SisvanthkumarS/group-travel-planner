import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { login, logout, register as registerUser } from '../api/auth';
import { onUnauthorized } from '../api/client';
import type { User } from '../api/types';
import {
  AUTH_CHANNEL,
  restoreSession,
  toLoginRequest,
  toRegisterRequest,
  writeCachedUser,
  type AuthMessage,
  type RegisterFields,
} from './session';

type AuthState =
  | { status: 'loading' }
  | { status: 'signedIn'; user: User }
  // byUser: the user chose to sign out (here or in another tab), so the next
  // sign-in should not jump back to the page they were on. An expired session
  // leaves it unset, so signing back in returns them where they were.
  | { status: 'signedOut'; byUser?: boolean };

type AuthContextValue = {
  state: AuthState;
  user: User | null;
  signIn: (identifier: string, password: string) => Promise<User>;
  /** Registers, then signs in so the user lands on their trips (US-01). */
  register: (fields: RegisterFields) => Promise<User>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function openChannel(): BroadcastChannel | null {
  return typeof BroadcastChannel === 'undefined'
    ? null
    : new BroadcastChannel(AUTH_CHANNEL);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const channel = useRef<BroadcastChannel | null>(null);

  const startSession = useCallback((user: User) => {
    writeCachedUser(user);
    setState({ status: 'signedIn', user });
  }, []);

  // Drop everything private: cached user, cached trip data, auth state.
  const endSession = useCallback(
    (byUser = false) => {
      writeCachedUser(null);
      queryClient.clear();
      setState({ status: 'signedOut', byUser });
    },
    [queryClient],
  );

  // Restore the session once on load.
  useEffect(() => {
    let cancelled = false;
    restoreSession()
      .then((user) => {
        if (cancelled) return;
        if (user) startSession(user);
        else setState({ status: 'signedOut' });
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'signedOut' });
      });
    return () => {
      cancelled = true;
    };
  }, [startSession]);

  // An expired or missing cookie on any authenticated request signs us out.
  useEffect(
    () =>
      onUnauthorized(() => {
        endSession();
        navigate('/sign-in', { replace: true });
      }),
    [endSession, navigate],
  );

  // Keep tabs in sync.
  useEffect(() => {
    const bc = openChannel();
    channel.current = bc;
    if (!bc) return;
    bc.onmessage = (event: MessageEvent<AuthMessage>) => {
      if (event.data.type === 'signed-out') {
        endSession(true);
        navigate('/sign-in', { replace: true });
      } else if (event.data.type === 'signed-in') {
        queryClient.clear();
        startSession(event.data.user);
      }
    };
    return () => {
      bc.close();
      channel.current = null;
    };
  }, [endSession, startSession, navigate, queryClient]);

  const signIn = useCallback(
    async (identifier: string, password: string) => {
      const user = await login(toLoginRequest(identifier, password));
      queryClient.clear();
      startSession(user);
      channel.current?.postMessage({
        type: 'signed-in',
        user,
      } satisfies AuthMessage);
      return user;
    },
    [queryClient, startSession],
  );

  const register = useCallback(
    async (fields: RegisterFields) => {
      const request = toRegisterRequest(fields);
      await registerUser(request);
      return signIn(request.email, request.password);
    },
    [signIn],
  );

  const signOut = useCallback(async () => {
    try {
      await logout();
    } catch {
      // Clear the local session even if the request fails.
    }
    endSession(true);
    channel.current?.postMessage({ type: 'signed-out' } satisfies AuthMessage);
    navigate('/sign-in', { replace: true });
  }, [endSession, navigate]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      user: state.status === 'signedIn' ? state.user : null,
      signIn,
      register,
      signOut,
    }),
    [state, signIn, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('useAuth requires AuthProvider');
  return auth;
}
