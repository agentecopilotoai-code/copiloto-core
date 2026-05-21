/**
 * UI-INFLU-015 — Container del módulo "Proveedores IA" (platform_owner only).
 *
 * `AIProviders.jsx` es presentacional puro (recibe `rows`/`health`/`onSave`/
 * `onTestProvider` por props). Este container conecta esas props al backend:
 *   - `GET /v1/platform/ai-providers` → `rows`
 *   - `PATCH /v1/platform/ai-providers/{modality}` → `onSave`
 *
 * No expone `ciphertext` ni `secret_value`: el backend solo devuelve `hint`.
 */
import { useCallback, useEffect, useState } from 'react';

import { AlertBanner } from '../../../components/ui/index.js';
import { LoadingScreen } from '../../../components/layout/LoadingScreen.jsx';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { listAIProviders, updateAIProvider } from '../../../services/coreApi.js';
import { AIProviders } from './AIProviders.jsx';

export function AIProvidersContainer() {
  const { session } = useTenantContext();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!session) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listAIProviders(session)
      .then((response) => {
        if (cancelled) return;
        setRows(Array.isArray(response?.items) ? response.items : []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar la config de proveedores IA');
        setRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, reloadToken]);

  const handleSave = useCallback(async (modality, payload) => {
    try {
      await updateAIProvider(session, modality, payload);
      setReloadToken((n) => n + 1);
    } catch (err) {
      setError(err?.message || `No se pudo actualizar la modalidad "${modality}"`);
      throw err;
    }
  }, [session]);

  if (loading) return <LoadingScreen />;

  return (
    <>
      {error ? (
        <AlertBanner tone="danger" title="Error" body={error} />
      ) : null}
      <AIProviders rows={rows} onSave={handleSave} />
    </>
  );
}
