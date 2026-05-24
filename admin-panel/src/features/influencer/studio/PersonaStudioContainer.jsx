/**
 * UI-INFLU-005 wiring — Container que cablea `PersonaStudio` con:
 *
 *  - `GET /v1/influencer/personas/{personaId}/studio` (bundle del detalle)
 *  - `GET /v1/influencer/credits` (balance para validar costo en composer)
 *  - `POST /v1/influencer/personas/{personaId}/generate` (composer inline)
 *  - `POST /v1/influencer/personas/{personaId}/face/reference` (upload de
 *    foto de referencia para `params.reference_image_url`)
 *  - Navegación al calendar con `?generation_id=` para "Programar post"
 *
 * Polling (UI-INFLU-014.13):
 * - El POST /generate encola un job (`status='queued'`). El worker lo
 *   procesa, crea assets, y mueve a `status='succeeded'|'failed'`. Para
 *   reflejar este cambio sin que el usuario tenga que refrescar:
 *   * Si en el bundle hay alguna generación con `status in (queued,running)`
 *     refrescamos cada 5s.
 *   * Cuando ninguna esté pendiente, paramos el polling.
 *
 * Ruta: `/t/:tenantSlug/influencer/personas/:personaId/studio`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';

import { useAuth } from '../../../context/AuthContext.jsx';
import {
  generateContent,
  getCreditsBalance,
  getPersonaStudio,
  uploadPersonaReference,
} from '../../../services/coreApi.js';
import { PersonaStudio } from './PersonaStudio.jsx';


const POLL_INTERVAL_MS = 5000;


function hasPendingGenerations(studio) {
  const items = studio?.recent_generations || [];
  return items.some((g) => g.status === 'queued' || g.status === 'running');
}


export function PersonaStudioContainer() {
  const { tenantSlug, personaId } = useParams();
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const navigate = useNavigate();
  const tenantId = activeTenant?.id;

  const [studio, setStudio] = useState(null);
  const [balance, setBalance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const pollTimerRef = useRef(null);

  // Fetch initial + cuando refreshKey cambia (manual o por polling).
  useEffect(() => {
    if (!session || !tenantId || !personaId) return undefined;
    let cancelled = false;
    if (refreshKey === 0) setLoading(true);
    setError(null);
    Promise.allSettled([
      getPersonaStudio(session, tenantId, personaId),
      getCreditsBalance(session, tenantId),
    ]).then(([studioRes, balanceRes]) => {
      if (cancelled) return;
      if (studioRes.status === 'fulfilled') {
        setStudio(studioRes.value);
      } else if (refreshKey === 0) {
        // Solo seteamos error en el primer fetch — un refresh por polling
        // que falle (red intermitente) NO debe mostrar pantalla de error.
        setError(studioRes.reason?.message || 'Error cargando el personaje');
      }
      if (balanceRes.status === 'fulfilled') {
        setBalance(balanceRes.value?.balance ?? 0);
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, personaId, refreshKey]);

  // Polling: cuando el bundle tiene generaciones queued/running, refrescamos
  // cada 5s. Limpia el timer cuando ya no hay pendientes o al unmount.
  useEffect(() => {
    if (!studio) return undefined;
    const pending = hasPendingGenerations(studio);
    if (!pending) {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return undefined;
    }
    pollTimerRef.current = setTimeout(() => {
      setRefreshKey((k) => k + 1);
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [studio]);

  const handleGenerate = useCallback(async (payload) => {
    if (!session || !tenantId || !personaId) return;
    await generateContent(session, tenantId, personaId, payload);
    // Refresca el bundle de inmediato — el job nuevo aparece con
    // status='queued' y dispara el polling hasta que termine.
    setRefreshKey((k) => k + 1);
  }, [session, tenantId, personaId]);

  const handleUploadReference = useCallback(async (file) => {
    if (!session || !tenantId || !personaId) return null;
    return uploadPersonaReference(session, tenantId, personaId, file);
  }, [session, tenantId, personaId]);

  const handleSchedulePost = useCallback((generation) => {
    const id = typeof generation === 'string'
      ? generation
      : (generation?.id || generation?.generation_id);
    if (!id) {
      navigate(`/t/${tenantSlug}/influencer/influencer-calendar`);
      return;
    }
    navigate(`/t/${tenantSlug}/influencer/influencer-calendar?generation_id=${id}`);
  }, [navigate, tenantSlug]);

  return (
    <PersonaStudio
      studio={studio}
      loading={loading}
      error={error}
      balance={balance}
      onGenerate={handleGenerate}
      onSchedulePost={handleSchedulePost}
      onUploadReference={handleUploadReference}
    />
  );
}
