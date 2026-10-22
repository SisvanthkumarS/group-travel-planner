import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import './style.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <main>
          <Link to="/">Group Travel Planner</Link>
          <Routes>
            <Route
              path="/"
              element={
                <>
                  <h1>Plan your next trip together</h1>
                  <p>
                    Project scaffold ready. Trips, voting, and itinerary
                    features will follow the API design.
                  </p>
                </>
              }
            />
            <Route path="*" element={<h1>Page not found</h1>} />
          </Routes>
        </main>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
);
