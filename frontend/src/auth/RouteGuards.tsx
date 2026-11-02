import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider';

type FromState = { from?: string } | null;

function SessionLoading() {
  return (
    <div className="page-loading" role="status">
      Loading…
    </div>
  );
}

/** Private pages: signed-out visitors go to sign-in and come back after (US-03). */
export function RequireAuth() {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === 'loading') return <SessionLoading />;
  if (state.status === 'signedOut') {
    return (
      <Navigate
        to="/sign-in"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }
  return <Outlet />;
}

/** Sign-in and register: a signed-in user goes straight to their trips. */
export function RedirectIfSignedIn() {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === 'loading') return <SessionLoading />;
  if (state.status === 'signedIn') {
    const from = (location.state as FromState)?.from;
    return <Navigate to={from ?? '/trips'} replace />;
  }
  return <Outlet />;
}
