/**
 * useGdScope — hook global del módulo GD para el "alcance" activo.
 *
 * El alcance es un selector que aparece en el topbar GD y filtra todas las
 * queries del módulo (mis tareas, radicados, PQRSD, etc.) a uno de los 3
 * niveles. El backend evalúa el alcance vía `gd.asignacion_alcance` y RLS;
 * este hook solo lo pasa como query param para que el server lo aplique.
 *
 * - `propio`: solo lo que está asignado a mí (rol operativo).
 * - `dependencias_autorizadas`: lo que mi rol puede ver dentro de su árbol
 *   de dependencias (jefe, coordinador VU, admin PQRSD).
 * - `institucional`: toda la entidad (auditor, admin sistema).
 *
 * Persistencia: localStorage por tenant. Se reinicia al cambiar de tenant.
 */
import { useCallback, useEffect, useState } from 'react';

const SCOPES = Object.freeze(['propio', 'dependencias_autorizadas', 'institucional']);
const DEFAULT_SCOPE = 'propio';

const storageKey = (tenantSlug) => `gd_scope__${tenantSlug || 'global'}`;

export function useGdScope(tenantSlug) {
  const [scope, setScopeState] = useState(() => readInitial(tenantSlug));

  // Re-sincronizar si cambia el tenant.
  useEffect(() => {
    setScopeState(readInitial(tenantSlug));
  }, [tenantSlug]);

  const setScope = useCallback(
    (next) => {
      if (!SCOPES.includes(next)) return;
      setScopeState(next);
      try {
        if (typeof window !== 'undefined' && window.localStorage) {
          window.localStorage.setItem(storageKey(tenantSlug), next);
        }
      } catch {
        /* no-op: si localStorage no está disponible (ej. SSR), no fallar */
      }
    },
    [tenantSlug],
  );

  return { scope, setScope, scopes: SCOPES };
}

function readInitial(tenantSlug) {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      const stored = window.localStorage.getItem(storageKey(tenantSlug));
      if (stored && SCOPES.includes(stored)) return stored;
    }
  } catch {
    /* no-op */
  }
  return DEFAULT_SCOPE;
}

export const GD_SCOPE_LABELS = Object.freeze({
  propio: 'Mi dependencia',
  dependencias_autorizadas: 'Mis dependencias autorizadas',
  institucional: 'Toda la entidad',
});
