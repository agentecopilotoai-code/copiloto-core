import { RouterProvider } from 'react-router-dom';

import { appRouter } from './app/router.jsx';
import { LoadingScreen } from './components/layout/LoadingScreen.jsx';
import { LoginScreen } from './components/layout/LoginScreen.jsx';
import { useAuth } from './context/AuthContext.jsx';

export function App() {
  const { error, isAuthenticated, isLoading } = useAuth();

  if (isLoading) return <LoadingScreen />;
  if (!isAuthenticated) return <LoginScreen error={error} />;

  return <RouterProvider router={appRouter} />;
}
