/**
 * Container del módulo Email Providers (v2.0.0, platform_owner only).
 *
 * Conecta las props presentacionales de `EmailProviders.jsx` a la API:
 *   - `GET    /v1/platform/email-providers`           → `rows`
 *   - `POST   /v1/platform/email-providers`           → `onCreate`
 *   - `PATCH  /v1/platform/email-providers/{id}`      → `onPatch`
 *   - `DELETE /v1/platform/email-providers/{id}`      → `onDelete`
 *   - `POST   /v1/platform/email-providers/{id}/test` → `onTest`
 */
import { useCallback, useEffect, useState } from 'react';

import { AlertBanner } from '../../../components/ui/index.js';
import { LoadingScreen } from '../../../components/layout/LoadingScreen.jsx';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import {
  createEmailProvider,
  deleteEmailProvider,
  listEmailProviders,
  patchEmailProvider,
  testEmailProvider,
} from '../../../services/coreApi.js';
import { EmailProviders } from './EmailProviders.jsx';

export function EmailProvidersContainer() {
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
    listEmailProviders(session)
      .then((response) => {
        if (cancelled) return;
        setRows(Array.isArray(response?.rows) ? response.rows : []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar la lista de providers de email');
        setRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [session, reloadToken]);

  const refresh = useCallback(() => setReloadToken((n) => n + 1), []);

  const onCreate = useCallback(async (payload) => {
    try {
      await createEmailProvider(session, payload);
      refresh();
    } catch (err) {
      setError(err?.message || 'No se pudo crear el provider');
      throw err;
    }
  }, [session, refresh]);

  const onPatch = useCallback(async (id, payload) => {
    try {
      await patchEmailProvider(session, id, payload);
      refresh();
    } catch (err) {
      setError(err?.message || 'No se pudo actualizar el provider');
      throw err;
    }
  }, [session, refresh]);

  const onDelete = useCallback(async (id) => {
    try {
      await deleteEmailProvider(session, id);
      refresh();
    } catch (err) {
      setError(err?.message || 'No se pudo borrar el provider');
      throw err;
    }
  }, [session, refresh]);

  const onTest = useCallback(async (id, payload) => {
    return testEmailProvider(session, id, payload);
  }, [session]);

  if (loading) return <LoadingScreen />;

  return (
    <>
      {error ? (
        <AlertBanner tone="danger" title="Error">{error}</AlertBanner>
      ) : null}
      <EmailProviders
        rows={rows}
        onCreate={onCreate}
        onPatch={onPatch}
        onDelete={onDelete}
        onTest={onTest}
      />
    </>
  );
}
