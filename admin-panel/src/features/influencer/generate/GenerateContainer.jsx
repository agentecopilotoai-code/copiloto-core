/**
 * UI-INFLU-013 wiring — Container del composer "Generar contenido".
 *
 * `Generate.jsx` es presentacional: recibe `balance`, `recentGenerations`,
 * y callbacks (`onGenerate`, `onTopUp`, `onSchedulePost`, etc.). Este
 * container:
 *
 *   - Resuelve `personaId` del URL.
 *   - Fetcha `balance` (TASK-INFLU-016) y `recentGenerations` (TASK-INFLU-011)
 *     en paralelo.
 *   - Cablea `onGenerate` → `POST /personas/{id}/generate` (worker async
 *     procesa el job en background; el response trae el `generation_id`).
 *   - `onTopUp` → navega a la vista de créditos.
 *
 * Ruta: `/t/:tenantSlug/influencer/personas/:personaId/generate`.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';

import { useAuth } from '../../../context/AuthContext.jsx';
import {
  generateContent,
  getCreditsBalance,
  listGenerations,
} from '../../../services/coreApi.js';
import { Generate } from './Generate.jsx';

export function GenerateContainer() {
  const { tenantSlug, personaId } = useParams();
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const navigate = useNavigate();
  const tenantId = activeTenant?.id;

  const [balance, setBalance] = useState(0);
  const [recentGenerations, setRecentGenerations] = useState([]);
  const [providerDown, setProviderDown] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!session || !tenantId || !personaId) return undefined;
    let cancelled = false;
    Promise.allSettled([
      getCreditsBalance(session, tenantId),
      listGenerations(session, tenantId, personaId, { limit: 12 }),
    ]).then(([balanceRes, genRes]) => {
      if (cancelled) return;
      if (balanceRes.status === 'fulfilled') {
        setBalance(balanceRes.value?.balance ?? 0);
      }
      if (genRes.status === 'fulfilled') {
        const items = genRes.value?.generations ?? genRes.value ?? [];
        setRecentGenerations(Array.isArray(items) ? items : []);
      }
      // Si TODOS los requests fallaron con error de provider, marcar
      // providerDown para que el componente muestre el empty state
      // específico (UI-INFLU-006).
      const allFailed = balanceRes.status === 'rejected' && genRes.status === 'rejected';
      const looksProvider = balanceRes.reason?.status >= 500 || genRes.reason?.status >= 500;
      setProviderDown(allFailed && looksProvider);
    });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, personaId, refreshKey]);

  const handleGenerate = useCallback(async (payload) => {
    await generateContent(session, tenantId, personaId, payload);
    // Refrescar balance + lista para reflejar el debit y el nuevo job
    // pending. El worker async procesa el job en background; el user
    // ve "pendiente" → "completado" cuando vuelva a entrar.
    setRefreshKey((k) => k + 1);
  }, [session, tenantId, personaId]);

  const handleTopUp = useCallback(() => {
    navigate(`/t/${tenantSlug}/influencer/influencer-credits`);
  }, [navigate, tenantSlug]);

  const handleRetryProvider = useCallback(() => {
    setProviderDown(false);
    setRefreshKey((k) => k + 1);
  }, []);

  const handleSchedulePost = useCallback((generationId) => {
    // UI-INFLU-014 — abrir el calendar con el generation pre-seleccionado.
    // Por ahora, navegamos al calendar; el modal de "crear post" se
    // implementa cuando el composer del calendar lo necesite.
    navigate(
      `/t/${tenantSlug}/influencer/influencer-calendar?generation_id=${generationId}`,
    );
  }, [navigate, tenantSlug]);

  return (
    <Generate
      balance={balance}
      recentGenerations={recentGenerations}
      providerDown={providerDown}
      onGenerate={handleGenerate}
      onTopUp={handleTopUp}
      onRetryProvider={handleRetryProvider}
      onSchedulePost={handleSchedulePost}
    />
  );
}
