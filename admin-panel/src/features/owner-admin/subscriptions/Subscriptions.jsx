import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { PlanFormModal } from './components/PlanFormModal.jsx';
import { PlansPanel } from './components/PlansPanel.jsx';
import { SubscribersTable } from './components/SubscribersTable.jsx';
import { SubscriptionsKpis } from './components/SubscriptionsKpis.jsx';
import { useSubscriptionsData } from './hooks/useSubscriptionsData.js';
import styles from './Subscriptions.module.css';

/**
 * UI-007.6 — Negocio · Suscripciones.
 *
 * Redesign of the legacy `SubscriptionsModule`: a derived KPI grid, a plans
 * panel and a tabbed subscribers `DataTable`. Plans/subscribers state and the
 * mutation handlers live in the `useSubscriptionsData` hook; logic is preserved
 * verbatim. Gated by `subscriptions.write` (the backend remains the authority).
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/14 _ Negocio · Suscripciones.html`.
 * Declared difference: the HTML "Churn 30d" KPI is replaced by "Cancelados" and
 * MRR is derived from the active subscribers — no churn snapshot is modelled,
 * so no data is fabricated.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function Subscriptions({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useSubscriptionsData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="subscriptions.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Negocio"
          title={module?.label || 'Suscripciones'}
          description="Cobros recurrentes vía Stripe y MercadoPago. Cuando un cobro falla, el cliente recibe una notificación automática por WhatsApp."
          actions={
            <button
              type="button"
              className={styles.primaryButton}
              onClick={actions.openCreate}
              disabled={!state.tenantId}
            >
              Nuevo plan
            </button>
          }
        />

        {state.error ? (
          <AlertBanner
            tone="danger"
            title={state.error}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissError}
              >
                Cerrar
              </button>
            }
          />
        ) : null}

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para gestionar sus suscripciones."
            />
          </Card>
        ) : (
          <>
            <SubscriptionsKpis kpis={state.kpis} />
            <PlansPanel
              plans={state.plans}
              loading={state.loading}
              saving={state.saving}
              onEdit={actions.openEdit}
              onArchive={actions.archivePlan}
            />
            <SubscribersTable
              subscribers={state.visibleSubscribers}
              allSubscribers={state.subscribers}
              tab={state.subscriberTab}
              loading={state.loading}
              saving={state.saving}
              onTabChange={actions.setSubscriberTab}
              onCancel={actions.cancelSubscription}
            />
          </>
        )}

        <PlanFormModal
          open={state.modalOpen}
          form={state.form}
          saving={state.saving}
          onFieldChange={actions.setFormField}
          onSubmit={actions.save}
          onClose={actions.closeModal}
        />
      </section>
    </RequirePermission>
  );
}
