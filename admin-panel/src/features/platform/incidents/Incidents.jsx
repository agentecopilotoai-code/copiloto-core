import { useState } from 'react';

import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { IncidentDrawer } from './components/IncidentDrawer.jsx';
import { IncidentFilters } from './components/IncidentFilters.jsx';
import { IncidentKpis } from './components/IncidentKpis.jsx';
import { IncidentsTable } from './components/IncidentsTable.jsx';
import { usePlatformIncidents } from './hooks/usePlatformIncidents.js';
import styles from './Incidents.module.css';

/**
 * UI-006.4 — Incidentes.
 *
 * Platform-owner cross-tenant view of `app.operator_alerts` (TASK-0057 /
 * TASK-0064 / TASK-0065): the alerts that fired across the fleet, with a
 * derived severity and runbook reference per kind. Reads
 * `GET /v1/platform/incidents` (router-protected by `require_platform_owner` +
 * `require_mfa_for_privileged`).
 *
 * Visual reference: `docs/HTML DESIGN/Platform Owner/04 _ Incidentes.html`.
 * Intentional difference: the HTML shows assignees, MTTR, postmortem links and
 * "Marcar resuelto" / "Nuevo incidente" write actions; those need an incident-
 * management schema that does not exist — deferred to a backend ticket. This
 * view is the read-only fleet feed.
 */
export function Incidents() {
  const { session, profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant: null });
  const [filters, setFilters] = useState({});
  const [selected, setSelected] = useState(null);

  const { incidents, summary, note, loading, error, refresh } = usePlatformIncidents({
    session,
    filters: { ...filters, limit: 200 },
  });

  return (
    <RequirePermission permissions={permissions} capability="platform.incidents.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Operaciones"
          title="Incidentes"
          description="Feed cross-tenant de alertas de operador (TASK-0057 / TASK-0064 / TASK-0065). Cada tipo de alerta deriva una severidad y, cuando aplica, un runbook publicado."
          actions={
            <button type="button" className={styles.refreshButton} onClick={refresh}>
              Actualizar
            </button>
          }
        />

        {error && !summary ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar Incidentes"
              description={error}
              action={
                <button type="button" className={styles.refreshButton} onClick={refresh}>
                  Reintentar
                </button>
              }
            />
          </Card>
        ) : (
          <>
            <IncidentKpis summary={summary || {}} />

            <Card padding="md">
              <IncidentFilters filters={filters} onChange={setFilters} />
              <IncidentsTable
                rows={incidents}
                loading={loading}
                error={error}
                onSelect={setSelected}
                onRetry={refresh}
              />
            </Card>

            {note ? <p className={styles.note}>{note}</p> : null}
          </>
        )}

        <IncidentDrawer incident={selected} onClose={() => setSelected(null)} />
      </section>
    </RequirePermission>
  );
}
