import { Link, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { initials } from '../auth/session';
import { BrandMark } from './BrandMark';

/** Header and page frame for every signed-in screen. */
export function AppLayout() {
  const { user, signOut } = useAuth();

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__inner">
          <Link to="/trips" className="app-header__brand">
            <BrandMark />
            <span>Group Travel Planner</span>
          </Link>
          {user && (
            <div className="app-header__user">
              <span className="avatar" aria-hidden="true">
                {initials(user.user_name)}
              </span>
              <span className="app-header__name">{user.user_name}</span>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={signOut}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>
      <Outlet />
    </div>
  );
}
