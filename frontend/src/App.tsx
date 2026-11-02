import { Navigate, Route, Routes } from 'react-router-dom';
import { RedirectIfSignedIn, RequireAuth } from './auth/RouteGuards';
import { AppLayout } from './components/AppLayout';
import { NotFoundPage } from './pages/NotFoundPage';
import { RegisterPage } from './pages/RegisterPage';
import { SignInPage } from './pages/SignInPage';
import { TripsPage } from './pages/TripsPage';

export function App() {
  return (
    <Routes>
      <Route element={<RedirectIfSignedIn />}>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/trips" element={<TripsPage />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/trips" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
