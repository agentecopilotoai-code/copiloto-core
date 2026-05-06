import { createContext, useContext, useEffect, useMemo, useState } from 'react';

import { fetchAdminSession } from '../services/adminSession.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    fetchAdminSession()
      .then((nextSession) => {
        if (!mounted) return;
        setSession(nextSession);
        setStatus(nextSession ? 'authenticated' : 'anonymous');
      })
      .catch((nextError) => {
        if (!mounted) return;
        setError(nextError);
        setStatus('error');
      });

    return () => {
      mounted = false;
    };
  }, []);

  const value = useMemo(
    () => ({
      error,
      isAuthenticated: status === 'authenticated',
      isLoading: status === 'loading',
      session,
      status,
    }),
    [error, session, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth debe usarse dentro de AuthProvider.');
  }
  return context;
}
