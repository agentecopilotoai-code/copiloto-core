import { createContext, useContext, useEffect, useMemo, useState } from 'react';

import { fetchAdminSession, SESSION_UNAUTHORIZED } from '../services/adminSession.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  // M46 — razón del último 401, expuesta al frontend para mostrar
  // mensajes específicos ("tu sesión expiró" vs "iniciá sesión"). Solo
  // tiene valor cuando status === 'anonymous'.
  const [unauthorizedReason, setUnauthorizedReason] = useState(null);

  useEffect(() => {
    let mounted = true;

    fetchAdminSession()
      .then((result) => {
        if (!mounted) return;
        if (result?.unauthorized === SESSION_UNAUTHORIZED) {
          setSession(null);
          setUnauthorizedReason(result.reason);
          setStatus('anonymous');
        } else {
          setSession(result);
          setUnauthorizedReason(null);
          setStatus(result ? 'authenticated' : 'anonymous');
        }
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
      unauthorizedReason,
    }),
    [error, session, status, unauthorizedReason],
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
