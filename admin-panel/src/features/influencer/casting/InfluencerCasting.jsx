/**
 * UI-INFLU-014.6 — `InfluencerCasting` carga `/v1/influencer/casting`
 * con `coreApi.getCasting()` y renderiza:
 *   - `CastingEmptyState` cuando `personas=[]`,
 *   - `Casting` cuando hay al menos un personaje (incluyendo drafts).
 *
 * Antes este componente NUNCA llamaba al backend (el comentario lo
 * decía: "UI-INFLU-004 inyectará el fetch real"). Resultado: aunque
 * existían personas en DB, el UI siempre mostraba empty state. Bug
 * reportado por el usuario el 2026-05-22.
 *
 * El prop `casting` se mantiene para que los tests existentes (que
 * inyectan un mock) sigan funcionando sin red.
 */
import { useEffect, useState } from 'react';

import { Card, AlertBanner } from '../../../components/ui/index.js';
import { useAuth } from '../../../context/AuthContext.jsx';
import { useActiveTenant } from '../../../hooks/useActiveTenant.js';
import { getCasting } from '../../../services/coreApi.js';
import { Casting } from './Casting.jsx';
import { CastingEmptyState } from './CastingEmptyState.jsx';

export function InfluencerCasting({ casting: castingProp = null, loading: loadingProp = false }) {
  const { session } = useAuth();
  const activeTenant = useActiveTenant();
  const tenantId = activeTenant?.id;

  const [casting, setCasting] = useState(castingProp);
  const [loading, setLoading] = useState(loadingProp || castingProp === null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (castingProp !== null) {
      // Caller ya inyectó datos (tests, server-side render preflight, etc.).
      setCasting(castingProp);
      setLoading(false);
      return undefined;
    }
    if (!session || !tenantId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const data = await getCasting(session, tenantId);
        if (!cancelled) {
          setCasting(data);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'No se pudo cargar el casting');
          setCasting({ kpis: { active_personas: 0 }, personas: [] });
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [castingProp, session, tenantId]);

  if (loading) {
    return (
      <Card padding="lg">
        <p style={{ margin: 0 }} role="status" aria-live="polite">
          Cargando casting…
        </p>
      </Card>
    );
  }

  if (error) {
    return (
      <AlertBanner tone="warning">
        {error}
      </AlertBanner>
    );
  }

  if (!casting || (casting.personas?.length ?? 0) === 0) {
    return <CastingEmptyState />;
  }

  return <Casting casting={casting} />;
}
