import { AdminLayout } from './components/layout/AdminLayout.jsx';
import { LoginScreen } from './components/layout/LoginScreen.jsx';
import { LoadingScreen } from './components/layout/LoadingScreen.jsx';
import { useAuth } from './context/AuthContext.jsx';

export function App() {
  const { error, isAuthenticated, isLoading, session } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <LoginScreen error={error} />;
  }

  return <AdminLayout session={session} />;
}
