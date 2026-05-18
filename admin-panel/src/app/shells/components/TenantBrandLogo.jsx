import { useEffect, useState } from 'react';

import { fetchTenantMediaBlobUrl } from '../../../services/coreApi.js';
import styles from './TenantBrandLogo.module.css';

/**
 * UI-012 — Slot de logo personalizado del tenant. Si el backend expone
 * `tenant.brand_logo_url`, renderiza un `<img>`; en su defecto cae a las
 * iniciales del tenant (mismo helper que `TenantSwitcher`).
 *
 * BUG-177 (codex P1 sobre BUG-096): el `brand_logo_url` que persiste el
 * backend ahora es un path al proxy `/v1/tenants/{id}/media/{asset_id}/content`
 * (BUG-096), que requiere `Authorization: Bearer <token>`. El browser NO
 * manda esos headers en `<img src>`, así que un naïve `<img src={logoUrl}>`
 * recibe 401 → imagen rota. Fix: fetchear con auth (`fetchTenantMediaBlobUrl`),
 * convertir a `blob:` object URL, y asignárselo al `<img>`. Cleanup
 * revoca el blob al desmontar / al cambiar de URL para no leak memoria.
 *
 * URLs externas (http/https) se siguen renderizando directo (back-compat
 * con tenants que apuntan a CDN propio).
 *
 * El componente es **defensivo**: acepta `tenant = null/undefined` y siempre
 * devuelve algo renderizable (fallback genérico `"C"` de CopilotoIA).
 *
 * @param {{ session?: object, tenant?: { id?: string, brand_logo_url?: string, display_name?: string, slug?: string, name?: string } }} props
 */
function tenantLabel(tenant) {
  return tenant?.display_name || tenant?.name || tenant?.slug || 'CopilotoIA';
}

function tenantInitials(tenant) {
  const source = tenant?.display_name || tenant?.name || tenant?.slug || 'CO';
  const cleaned = source.replace(/[^a-zA-Z0-9]/g, '');
  return cleaned.slice(0, 2).toUpperCase() || 'CO';
}

function isExternalUrl(url) {
  return /^https?:\/\//i.test(url);
}

export function TenantBrandLogo({ session, tenant }) {
  const logoUrl = tenant?.brand_logo_url;
  const tenantId = tenant?.id;
  const label = tenantLabel(tenant);
  const [resolvedSrc, setResolvedSrc] = useState(null);

  useEffect(() => {
    // External URL (http/https CDN) → render directo, no fetch.
    if (!logoUrl) {
      setResolvedSrc(null);
      return undefined;
    }
    if (isExternalUrl(logoUrl)) {
      setResolvedSrc(logoUrl);
      return undefined;
    }
    // Proxy interno requiere auth → fetch como blob.
    if (!session || !tenantId) {
      // Sin session/tenantId no podemos auth — caemos a iniciales.
      setResolvedSrc(null);
      return undefined;
    }
    let revoked = false;
    let blobUrl = null;
    fetchTenantMediaBlobUrl(session, tenantId, logoUrl)
      .then((url) => {
        if (revoked) {
          URL.revokeObjectURL(url);
          return;
        }
        blobUrl = url;
        setResolvedSrc(url);
      })
      .catch(() => {
        // Fallback silencioso a las iniciales si el fetch falla.
        if (!revoked) setResolvedSrc(null);
      });
    return () => {
      revoked = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [logoUrl, session, tenantId]);

  if (resolvedSrc) {
    return (
      <img
        src={resolvedSrc}
        alt={`Logo de ${label}`}
        className={styles.logo}
      />
    );
  }

  return (
    <span
      className={styles.fallback}
      role="img"
      aria-label={`Logo de ${label}`}
    >
      {tenantInitials(tenant)}
    </span>
  );
}
