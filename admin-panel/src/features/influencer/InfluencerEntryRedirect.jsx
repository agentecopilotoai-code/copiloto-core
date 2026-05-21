import { Navigate, useParams } from 'react-router-dom';

/**
 * Redirect component para el módulo de nav `influencer-entry`.
 *
 * El item `influencer-entry` vive en `TENANT_NAV` como entry-point al
 * `InfluencerShell`. El click normal del menú lateral navega DIRECTAMENTE a
 * `/t/{slug}/influencer` desde `TenantShellRoute.onModuleSelect` (sin pasar
 * por este componente). Este componente solo se renderiza en el caso edge
 * de un DEEP-LINK directo a `/t/{slug}/influencer-entry`: lo redirige al
 * shell real con `<Navigate replace/>` para que la URL final sea consistente
 * con el resto del módulo (`/t/{slug}/influencer` → redirect interno a
 * `influencer-casting`).
 *
 * Usa `useParams` para obtener `tenantSlug` del path actual. `replace=true`
 * evita basura en el history del browser (el usuario no debería ver el
 * intermediate `/influencer-entry` al hacer back).
 */
export function InfluencerEntryRedirect() {
  const { tenantSlug } = useParams();
  return <Navigate to={`/t/${tenantSlug}/influencer`} replace />;
}
