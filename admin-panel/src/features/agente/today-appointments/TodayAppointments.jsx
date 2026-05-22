import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { DayAppointmentsSummary } from './components/DayAppointmentsSummary.jsx';
import { TodayAppointmentsList } from './components/TodayAppointmentsList.jsx';
import { useTodayAppointmentsData } from './hooks/useTodayAppointmentsData.js';
import { dayNavLabel } from './todayAppointmentsData.js';
import styles from './TodayAppointments.module.css';

/**
 * UI-009.5 — Hoy · Citas del día (Agente).
 *
 * Nueva vista del rol Agente: lista de las citas del día con su estado en vivo
 * (confirmada, sin confirmar, atendida, no-show). Reusa los componentes de
 * dominio `AppointmentCard` + `StatusBadge`. El hook `useTodayAppointmentsData`
 * trae la lista completa vía `listAppointments` (tenant-scoped server-side) y
 * aplica el filtro por día en cliente sobre `starts_at` — `listAppointments` no
 * expone un parámetro de fecha establecido en el frontend. Gateada por
 * `appointments.view` (modo R); el backend reverifica.
 *
 * Referencia visual: `docs/HTML DESIGN/Agente/32 _ Hoy _ Citas del día.html`.
 * Diferencias intencionales declaradas: el HTML muestra una grilla "Agenda"
 * recurso × franja horaria, KPIs de "Ocupación %" e "Ingreso proyectado" y un
 * CTA "Nueva cita" — `listAppointments` devuelve registros planos y no expone
 * carriles de agenda por recurso, ocupación ni monto proyectado, y la creación
 * de citas vive en el panel de contacto del Inbox; todo eso se difiere (no se
 * inventan datos ni se cablea un botón a la nada).
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function TodayAppointments({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, actions } = useTodayAppointmentsData({ session, tenant });
  const dayLabel = dayNavLabel(state.selectedDay);

  return (
    <RequirePermission permissions={permissions} capability="appointments.view" mode="R">
      <section className={styles.page} data-module="appointments">
        <PageHeader
          eyebrow="Hoy"
          title={module?.label || 'Citas del día'}
          description="Agenda del día con el estado en vivo de cada cita. Navega entre días y revisa quién falta por confirmar."
          actions={
            <div className={styles.dayNav}>
              <button
                type="button"
                className={styles.navButton}
                onClick={actions.goToPrevDay}
              >
                Día anterior
              </button>
              <button
                type="button"
                className={styles.navButtonPrimary}
                onClick={actions.goToToday}
              >
                Hoy
              </button>
              <button
                type="button"
                className={styles.navButton}
                onClick={actions.goToNextDay}
              >
                Mañana
              </button>
            </div>
          }
        />

        <p className={styles.dayLabel} aria-live="polite">
          {dayLabel}
        </p>

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver su agenda de citas."
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
                    className={styles.navButton}
                    onClick={actions.refresh}
                  >
                    Reintentar
                  </button>
                }
              />
            ) : null}

            <DayAppointmentsSummary counts={state.counts} />

            <TodayAppointmentsList
              appointments={state.dayAppointments}
              isLoading={state.isLoading}
              dayLabel={dayLabel}
            />
          </>
        )}
      </section>
    </RequirePermission>
  );
}
