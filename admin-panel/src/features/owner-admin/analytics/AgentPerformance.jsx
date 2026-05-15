import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  AlertBanner,
  Card,
  EmptyState,
  PageHeader,
} from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { getAnalyticsAgents } from '../../../services/coreApi.js';
import { AgentPerformanceTable } from '../../manager/analytics/components/AgentPerformanceTable.jsx';
import { AgentKpis } from './components/AgentKpis.jsx';
import { LoadDistribution } from './components/LoadDistribution.jsx';
import {
  DEFAULT_PRESET,
  RANGE_PRESETS,
  buildAgentsCsv,
  rangeFromPreset,
} from './agentPerformanceData.js';
import styles from './AgentPerformance.module.css';

/**
 * UI-016.3 — Negocio · Rendimiento del equipo (Owner / Admin).
 *
 * Vista self-contained alineada al HTML del diseñador en
 * `docs/HTML DESIGN/Transversales/23b _ Negocio _ Rendimiento del equipo.html`.
 * Renderiza:
 *   - PageHeader con eyebrow "Análisis" + selector de rango + botón "Exportar".
 *   - 4 KPIs superiores (Mensajes humanos / Handoffs cerrados / Ingreso
 *     atribuido / 1ª respuesta media), derivados de los totales de
 *     `analytics_agents`.
 *   - Tabla "Por persona" reusando la primitiva `AgentPerformanceTable` ya
 *     compartida con `features/manager/analytics` (UI-008.1) — sin duplicar
 *     markup, ordenada por defecto por ingreso atribuido.
 *   - Sección "Distribución de carga" (gráfica de barras horizontales por
 *     persona).
 *   - Botón "Exportar" genera CSV cliente-side con BOM UTF-8.
 *
 * Gated por `analytics.tenant.read`; el backend (`GET /v1/analytics/agents`)
 * sigue siendo la autoridad de scoping por tenant y de los filtros de rol.
 *
 * Diferencias declaradas vs el mockup:
 *   - Los deltas "▲ 48 vs mes anterior" / "▲ 24%" / "▼ 8s" no se renderizan
 *     porque `analytics_agents` no devuelve la ventana previa — se prefiere no
 *     fabricar el delta. (Una futura UI-016.3-FU podría disparar un segundo
 *     fetch sobre la ventana previa para calcularlos like-for-like.)
 *   - La utilización "92%" y los micro-insights "Diana al 92%" / "Recepción
 *     ahorró 184h" del mockup no están expuestos por el endpoint; se omiten
 *     en lugar de inventarse.
 *
 * @param {{
 *   module?: object,
 *   session: object,
 *   tenant?: object,
 *   range?: { fromDate?: string, toDate?: string },
 * }} props
 */
export function AgentPerformance({ module, session, tenant, range }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const tenantId = tenant?.id;

  const [preset, setPreset] = useState(DEFAULT_PRESET);
  const [agents, setAgents] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Si el contenedor entrega un rango (consumo histórico desde AnalyticsPanel),
  // se respeta; si no, derivamos uno a partir del preset interno.
  const effectiveRange = useMemo(() => {
    if (range && (range.fromDate || range.toDate)) return range;
    return rangeFromPreset(preset);
  }, [range, preset]);

  useEffect(() => {
    if (!tenantId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getAnalyticsAgents(session, tenantId, effectiveRange)
      .then((result) => {
        if (!cancelled) setAgents(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || 'No se pudieron cargar las métricas del equipo.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, effectiveRange, reloadToken]);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  const handleExport = useCallback(() => {
    if (!agents) return;
    const csv = buildAgentsCsv(agents, {
      tenantId,
      fromDate: effectiveRange.fromDate,
      toDate: effectiveRange.toDate,
    });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `rendimiento-equipo-${tenant?.slug || tenantId || 'tenant'}-${
      effectiveRange.toDate || new Date().toISOString().slice(0, 10)
    }.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }, [agents, tenant, tenantId, effectiveRange]);

  // El sort por defecto exigido por el backlog es ingreso atribuido.
  const [sortBy, setSortBy] = useState('revenue_attributed');

  return (
    <RequirePermission permissions={permissions} capability="analytics.tenant.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Análisis"
          title={module?.label || 'Rendimiento del equipo'}
          description="Cómo está rindiendo cada miembro: mensajes atendidos, handoffs cerrados, citas confirmadas e ingreso atribuido."
          actions={
            <div className={styles.headerActions}>
              <label className={styles.rangeLabel}>
                Rango
                <select
                  className={styles.rangeSelect}
                  value={preset}
                  onChange={(event) => setPreset(event.target.value)}
                  disabled={Boolean(range)}
                  aria-label="Rango de fechas"
                >
                  {RANGE_PRESETS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className={styles.exportButton}
                onClick={handleExport}
                disabled={!agents || loading}
              >
                Exportar
              </button>
              <button
                type="button"
                className={styles.exportButton}
                onClick={refresh}
                disabled={loading || !tenantId}
              >
                {loading ? 'Actualizando…' : 'Actualizar'}
              </button>
            </div>
          }
        />

        {error ? <AlertBanner tone="danger" title={error} /> : null}

        {!tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver el rendimiento por agente."
            />
          </Card>
        ) : loading && !agents ? (
          <Card padding="md">
            <EmptyState
              title="Cargando métricas del equipo…"
              description="Consultando analytics_agents para la ventana seleccionada."
            />
          </Card>
        ) : (
          <>
            <AgentKpis agents={agents} />
            <AgentPerformanceTable
              agents={agents}
              sortBy={sortBy}
              onSortChange={setSortBy}
            />
            <LoadDistribution agents={agents} />
          </>
        )}
      </section>
    </RequirePermission>
  );
}
