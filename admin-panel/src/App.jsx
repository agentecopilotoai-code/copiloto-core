import { RouterProvider } from 'react-router-dom';

import { appRouter } from './app/router.jsx';
import { LoadingScreen } from './components/layout/LoadingScreen.jsx';
import { LoginScreen } from './components/layout/LoginScreen.jsx';
import { ConfirmProvider, ToastProvider } from './components/ui/index.js';
import { useAuth } from './context/AuthContext.jsx';

export function App() {
  const { error, isAuthenticated, isLoading } = useAuth();

  // ToastProvider + ConfirmProvider (UI-011) wrap the whole app — including
  // the loading and login screens — so every shell and every feature can call
  // `useToast()` / `useConfirm()` via context without per-shell mounting.
  return (
    <ToastProvider>
      <ConfirmProvider>
        {isLoading ? (
          <LoadingScreen />
        ) : !isAuthenticated ? (
          <LoginScreen error={error} />
        ) : (
          <RouterProvider router={appRouter} />
        )}
      </ConfirmProvider>
    </ToastProvider>
  );
}
