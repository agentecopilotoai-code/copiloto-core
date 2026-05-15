import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { AppointmentsFilters } from './components/AppointmentsFilters.jsx';
import { AppointmentsList } from './components/AppointmentsList.jsx';
import { useViewerAppointmentsData } from './hooks/useViewerAppointmentsData.js';
import { APPOINTMENTS_DESCRIPTION } from './viewerAppointmentsData.js';
import styles from './ViewerAppointments.module.css';

/**
 * UI-010.3 — Viewer · Lectura · Citas.
 *
 * Listado paginado de citas en modo solo lectura: filtros (estado, rango de
 * fechas, búsqueda por cliente), paginación cliente-side y exportación CSV de
 * la selección actual ("solo filtros y export-to-CSV opcional" del spec del
 * backlog). Reusa el componente de dominio `AppointmentCard` para cada fila;
 * no se renderizan slots `actions` (criterio global UI-010 — Viewers no
 * obtienen acciones de fila). El hook `useViewerAppointmentsData` posee el
 * estado y el fetch contra `listAppointments` (tenant-scoped server-side); el
 * filtrado y la paginación corren en cliente sobre el campo real `starts_at`.
 *
 * Referencia visual: `docs/HTML DESIGN/Viewer/35 _ Lectura _ Citas.html`.
 * Diferencias intencionales declaradas: el HTML muestra (a) un gráfico de
 * «Citas por día · última semana» con día pico, (b) KPIs «Atendidas / No-shows
 * / Canceladas / Ticket promedio», (c) un panel «Estado de las citas · mayo»
 * en proporción, (d) un bloque «Próximas citas destacadas» con miniaturas y
 * (e) un CTA «Tomar handoff» por fila. Esos elementos asumen agregaciones
 * (proyección, ocupación, ticket promedio) y acciones de escritura que no
 * existen en el endpoint `listAppointments` (devuelve registros planos con
 * `status`, `starts_at`, `service_name`/`service_code`, `resource_name` y
 * `contact_label`). Se difieren — no se inventan datos ni se cablea CTAs de
 * escritura, en línea con el criterio global UI-010 («100% de las acciones
 * write deben estar ocultas»). El `ReadOnlyShell` (UI-002) ya añade el banner
 * permanente «Modo solo lectura».
 *
 * @param {{ module?: object, session: object, tenant: object }} props
 */
export function ViewerAppointments({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useViewerAppointmentsData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="appointments.view" mode="R">
      <section className={styles.page} data-module="viewer-appointments">
        <PageHeader
          eyebrow="Lectura"
          title={module?.label || 'Citas'}
          description={APPOINTMENTS_DESCRIPTION}
        />

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver el listado de citas."
            />
          </Card>
        ) : (
          <>
            {state.error ? (
              <AlertBanner
                tone="danger"
                title={state.error}
                action={
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={actions.refresh}
                  >
                    Reintentar
                  </button>
                }
              />
            ) : null}

            <AppointmentsFilters
              filters={state.filters}
              filteredCount={state.filteredCount}
              total={state.total}
              isBusy={state.isLoading}
              tenantId={state.tenantId}
              onChange={actions.setFilter}
              onReset={actions.resetFilters}
              onExportCsv={actions.exportCsv}
            />

            <AppointmentsList
              appointments={state.pagedAppointments}
              isLoading={state.isLoading}
              page={state.page}
              totalPages={state.totalPages}
              onPageChange={actions.setPage}
            />
          </>
        )}
      </section>
    </RequirePermission>
  );
}
