import { useOutletContext, useParams } from 'react-router-dom';

import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission, usePermissions } from '../../../permissions/index.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { ContactTimeline } from '../../owner-admin/conversations-contacts/index.js';
import { ContactProfileHeader } from './components/ContactProfileHeader.jsx';
import { contactDisplayName } from './contactProfileData.js';
import { useContactProfileData } from './hooks/useContactProfileData.js';
import styles from './ContactProfile.module.css';

/**
 * UI-009.3 — Operación · Ficha de contacto.
 *
 * Focused, read-only contact profile reachable via the deep-link route
 * `/t/:tenantSlug/contacts/:contactId`. Renders inside the TenantShell outlet:
 * the active tenant comes from `useOutletContext()`, the contact id from
 * `useParams()` and `{ profile, session }` from `useTenantContext()`. It is a
 * route element, so it takes no props.
 *
 * Reuses the `ContactCard` and `AppointmentCard` domain components (via
 * `ContactProfileHeader` and the reused `ContactTimeline`) plus the
 * `ContactTimeline` history panel from the conversations-contacts feature.
 * Gated by `contacts.view`; the backend stays the authority and
 * `getContactProfile` / `listContactConsent` are tenant-scoped server-side.
 *
 * Reference: `docs/HTML DESIGN/Agente/30 _ Operación _ Ficha de contacto.html`.
 * Diferencias intencionales declaradas: el HTML muestra LTV/NPS/No-shows como
 * KPIs, "Sede preferida", "Canal preferido", "Cumpleaños", "Productos activos"
 * y "Sin suscripciones activas" — ninguno está expuesto por `getContactProfile`
 * ni `listContactConsent`, así que se difieren (no se inventan datos). Tampoco
 * se agregan CTAs de mutación: la vista es de solo lectura.
 */
export function ContactProfile() {
  const outletContext = useOutletContext();
  const activeTenant = outletContext?.activeTenant ?? null;
  const { tenantSlug, contactId } = useParams();
  const { profile: userProfile, session } = useTenantContext();
  const permissions = usePermissions({ profile: userProfile, tenant: activeTenant });

  const { state, actions } = useContactProfileData({
    session,
    tenantId: activeTenant?.id,
    contactId,
  });

  const heading = state.profile
    ? contactDisplayName(state.profile.contact)
    : 'Ficha de contacto';

  return (
    <RequirePermission permissions={permissions} capability="contacts.view" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Operación · Contactos"
          title={heading}
          description="Vista enfocada del contacto: identidad, valor del cliente e historial de citas, conversaciones, referidos y consentimiento."
          actions={
            <button type="button" className={styles.refreshButton} onClick={actions.refresh}>
              Actualizar
            </button>
          }
        />

        {!activeTenant ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para ver la ficha del contacto."
            />
          </Card>
        ) : state.notFound ? (
          <Card padding="md">
            <EmptyState
              title="Contacto no encontrado"
              description="El contacto no existe o no pertenece a este tenant."
            />
          </Card>
        ) : state.error && !state.profile ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar la ficha"
              description={state.error}
              action={
                <button
                  type="button"
                  className={styles.refreshButton}
                  onClick={actions.refresh}
                >
                  Reintentar
                </button>
              }
            />
          </Card>
        ) : state.loading && !state.profile ? (
          <Card padding="md">
            <EmptyState
              title="Cargando ficha…"
              description="Consultando el perfil y el ledger de consentimiento del contacto."
            />
          </Card>
        ) : state.profile ? (
          <div className={styles.layout}>
            <ContactProfileHeader
              profile={state.profile}
              consent={state.consent}
              tenantSlug={tenantSlug}
            />
            <ContactTimeline profile={state.profile} consent={state.consent} />
          </div>
        ) : null}
      </section>
    </RequirePermission>
  );
}
