import { RouterProvider } from 'react-router-dom';

import { appRouter } from './app/router.jsx';
import { LoadingScreen } from './components/layout/LoadingScreen.jsx';
import { ConfirmProvider, ToastProvider } from './components/ui/index.js';
import { useAuth } from './context/AuthContext.jsx';

/**
 * Raíz del SPA.
 *
 * Antes de UI-017 había un splash legacy que se montaba arriba del Router
 * cuando `!isAuthenticated`, ocultando la landing comercial pública (UI-016.4).
 * UI-017 elimina ese splash: ahora el `RouterProvider` se monta SIEMPRE que la
 * sesión esté resuelta (autenticada o anónima), y es el `IndexRedirect` del
 * router quien decide qué pintar:
 *
 *  - sesión nula  → `<Landing />` (público, con CTA "Iniciar sesión" que dispara
 *                   el redirect Auth0 vía `/admin/login` — flujo BFF existente).
 *  - sesión válida → home del rol (`/platform/...` o `/t/:slug/...`).
 *
 * `LoadingScreen` se preserva mientras `AuthContext` está resolviendo la sesión
 * (estado `isLoading`) — en ese punto aún no sabemos si mostrar la landing
 * pública o redirigir al home del rol, así que evitamos el flash.
 */
export function App() {
  const { isLoading } = useAuth();

  // ToastProvider + ConfirmProvider (UI-011) wrap the whole app — including
  // the loading screen — so every shell and every feature can call
  // `useToast()` / `useConfirm()` via context without per-shell mounting.
  return (
    <ToastProvider>
      <ConfirmProvider>
        {isLoading ? <LoadingScreen /> : <RouterProvider router={appRouter} />}
      </ConfirmProvider>
    </ToastProvider>
  );
}
