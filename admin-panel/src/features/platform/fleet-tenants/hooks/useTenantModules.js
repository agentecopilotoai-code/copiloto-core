import { useCallback, useEffect, useMemo, useState } from 'react';

import { listTenantModules, updateTenantModule } from '../../../../services/coreApi.js';

// PLATFORM-MODULES-EXPAND
// Catálogo del frontend — debe seguir el orden visual deseado en el drawer.
// Cualquier módulo aquí debe estar en el CHECK constraint de
// `app.tenant_modules.module` (ver `infra/postgres/01-schema.sql` y
// `infra/postgres/03-migrations.sql`, sección PLATFORM-MODULES-EXPAND).
//
// El catálogo se exporta para que el test del panel pueda iterar sin
// hard-codear strings.
export const TENANT_MODULES_CATALOG = [
  {
    code: 'influencer',
    label: 'Influencer Studio',
    description: 'Personas virtuales, casting, generación de contenido, publicación programada.',
  },
  {
    code: 'chatbot',
    label: 'Chatbot conversacional',
    description: 'Núcleo de CopilotoIA — RAG, intent classifier, handoff, recordatorios.',
  },
  {
    code: 'widget_web',
    label: 'Widget web',
    description: 'Captura de leads desde el sitio del tenant + formulario embebido.',
  },
  {
    code: 'campaigns',
    label: 'Campañas y mensajes masivos',
    description: 'Segmentos, envíos por WhatsApp, attribution, funnel.',
  },
  {
    code: 'analytics',
    label: 'Analítica de negocio',
    description: 'Dashboards de KPIs, no-show, ingreso, retención, funnel de conversión.',
  },
  {
    code: 'payments',
    label: 'Pagos (Stripe / MercadoPago)',
    description: 'Links de pago, registro de cobros, webhooks fail-closed.',
  },
  {
    code: 'gestion_documental',
    label: 'Gestión Documental',
    description: 'Módulo externo — Ventanilla Única, PQRSD, correspondencia, TRD/TVD, expedientes, firmas, IA asistida.',
  },
];

/**
 * Hook que combina dos endpoints del backend platform-owner:
 *  1. GET /platform/tenant-modules?tenant_search=<slug>  → lista qué módulos
 *     tiene activos un tenant.
 *  2. PATCH /platform/tenant-modules/{tenant_id}/{module} → activa/desactiva.
 *
 * Construye una vista uniforme: para cada módulo del catálogo
 * `TENANT_MODULES_CATALOG`, devuelve una fila con `enabled`, `plan`,
 * `activated_at`, `notes`. Si el tenant nunca activó un módulo, la fila
 * aparece con `enabled=false` y campos null — el toggle parte de OFF
 * sin necesidad de seed.
 *
 * @param {object} options
 * @param {object} options.session — admin session
 * @param {{id: string, slug: string}} options.tenant — tenant cuyo panel se muestra
 * @returns {{
 *   rows: Array<{code: string, label: string, description: string, enabled: boolean, plan: string|null, activated_at: string|null, notes: string|null}>,
 *   loading: boolean,
 *   error: string|null,
 *   mutating: string|null,
 *   toggle: (moduleCode: string, nextEnabled: boolean) => Promise<void>,
 *   refresh: () => void
 * }}
 */
export function useTenantModules({ session, tenant }) {
  const [serverRows, setServerRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [mutating, setMutating] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const tenantId = tenant?.id ?? null;
  const tenantSlug = tenant?.slug ?? null;

  const refresh = useCallback(() => setReloadToken((n) => n + 1), []);

  useEffect(() => {
    if (!tenantId || !tenantSlug) {
      setServerRows([]);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    listTenantModules(session, { tenantSearch: tenantSlug })
      .then((response) => {
        if (cancelled) return;
        const items = Array.isArray(response?.items) ? response.items : [];
        // Filtramos client-side por tenant_id exacto — `tenant_search`
        // usa LIKE así que puede traer matches parciales (ej. slug "demo"
        // matchea "demo-1", "demo-2").
        const own = items.filter((row) => String(row.tenant_id) === String(tenantId));
        setServerRows(own);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo cargar el listado de módulos del tenant');
        setServerRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, tenantSlug, reloadToken]);

  // Combina el catálogo con las filas del backend. Si el tenant nunca activó
  // un módulo, no aparece en `serverRows` — lo presentamos con enabled=false.
  const rows = useMemo(() => {
    const byCode = new Map(serverRows.map((r) => [r.module, r]));
    return TENANT_MODULES_CATALOG.map((cat) => {
      const server = byCode.get(cat.code);
      return {
        code: cat.code,
        label: cat.label,
        description: cat.description,
        enabled: server ? Boolean(server.enabled) : false,
        plan: server?.plan ?? null,
        activated_at: server?.activated_at ?? null,
        activated_by: server?.activated_by ?? null,
        notes: server?.notes ?? null,
      };
    });
  }, [serverRows]);

  const toggle = useCallback(async (moduleCode, nextEnabled) => {
    if (!tenantId) return;
    setMutating(moduleCode);
    setError(null);
    try {
      const updated = await updateTenantModule(session, tenantId, moduleCode, {
        enabled: nextEnabled,
        plan: null,
        notes: null,
      });
      // Optimistic update local — si el backend respondió OK, reemplazamos
      // la fila por la versión nueva.
      setServerRows((prev) => {
        const without = prev.filter((r) => r.module !== moduleCode);
        return [...without, updated];
      });
    } catch (err) {
      setError(err?.message || `No se pudo cambiar el módulo "${moduleCode}".`);
      throw err;
    } finally {
      setMutating(null);
    }
  }, [session, tenantId]);

  return { rows, loading, error, mutating, toggle, refresh };
}
