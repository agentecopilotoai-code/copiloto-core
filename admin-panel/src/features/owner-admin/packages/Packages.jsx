import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { PackagesTable } from './components/PackagesTable.jsx';
import { PackageFormModal } from './components/PackageFormModal.jsx';
import { usePackagesData } from './hooks/usePackagesData.js';
import styles from './Packages.module.css';

/**
 * UI-007.5 — Negocio · Paquetes.
 *
 * Redesign of the legacy `PackagesModule`: the catalogue is now a `DataTable`
 * and the create/edit form moved into a `Modal`. Catalogue state and the
 * mutation handlers live in the `usePackagesData` hook; logic is preserved
 * verbatim. Gated by `packages.write` (the backend remains the authority).
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/13 _ Negocio _ Paquetes.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function Packages({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, actions } = usePackagesData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="packages.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Negocio"
          title={module?.label || 'Paquetes'}
          description="Planes multi-cita con saldo de sesiones. Al completar una cita asociada el saldo decrementa automáticamente; vencimiento y reglas se configuran por paquete."
          actions={
            <button
              type="button"
              className={styles.primaryButton}
              onClick={actions.openCreate}
              disabled={!state.tenantId}
            >
              Nuevo paquete
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
              description="Elige un tenant activo para gestionar su catálogo de paquetes."
            />
          </Card>
        ) : (
          <PackagesTable
            packages={state.packages}
            serviceMap={state.serviceMap}
            loading={state.loading}
            saving={state.saving}
            onEdit={actions.openEdit}
            onDeactivate={actions.deactivate}
          />
        )}

        <PackageFormModal
          open={state.modalOpen}
          form={state.form}
          services={state.services}
          saving={state.saving}
          // BUG-113: pasamos el error al modal para que se vea por encima del
          // backdrop. El AlertBanner del outer queda igualmente para errores
          // cuando el modal está cerrado (fetch inicial fallido, etc).
          error={state.modalOpen ? state.error : ''}
          onFieldChange={actions.setFormField}
          onToggleService={actions.toggleService}
          onSubmit={actions.save}
          onClose={actions.closeModal}
          onDismissError={actions.dismissError}
        />
      </section>
    </RequirePermission>
  );
}
