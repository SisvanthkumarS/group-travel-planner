import { createContext, useContext, useState, type ReactNode } from 'react';

type Auth = { token: string | null; setToken: (token: string | null) => void };
const AuthContext = createContext<Auth | undefined>(undefined);

// In-memory session scaffold. No login endpoint exists yet.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  return (
    <AuthContext.Provider value={{ token, setToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('useAuth requires AuthProvider');
  return auth;
}
