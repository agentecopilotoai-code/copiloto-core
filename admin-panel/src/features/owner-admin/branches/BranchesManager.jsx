import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { BranchFormDrawer } from './components/BranchFormDrawer.jsx';
import { BranchesList } from './components/BranchesList.jsx';
import { useBranchesData } from './hooks/useBranchesData.js';
import styles from './Branches.module.css';

/**
 * UI-007.7 — Negocio · Sedes: the full Sedes view (page header + list +
 * create/edit drawer). Ungated on purpose so it can be embedded both in the
 * permission-gated `Branches` module entry AND inside the Tenant Setup wizard's
 * "Sedes" tab (where the legacy `BranchesModule` was reused the same way).
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/15 _ Negocio · Sedes.html`.
 *
 * @param {{ module?: object, session: object, tenant: object }} props
 */
export function BranchesManager({ module, session, tenant }) {
  const { state, actions } = useBranchesData({ session, tenant });

  return (
    <section className={styles.page}>
      <PageHeader
        eyebrow="Negocio"
        title={module?.label || 'Sedes'}
        description="Cada sede tiene su propia dirección, horario y teléfono. Los recordatorios envían la dirección y el mapa de la sede de la cita; los analytics se pueden filtrar por sede."
        actions={
          <button
            type="button"
            className={styles.primaryButton}
            onClick={actions.openCreate}
            disabled={!state.tenantId}
          >
            Nueva sede
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
            description="Elige un tenant activo para gestionar sus sedes."
          />
        </Card>
      ) : (
        <BranchesList
          branches={state.branches}
          loading={state.loading}
          saving={state.saving}
          onEdit={actions.openEdit}
          onDeactivate={actions.deactivate}
        />
      )}

      <BranchFormDrawer
        open={state.drawerOpen}
        form={state.form}
        saving={state.saving}
        mapsPreviewUrl={state.mapsPreviewUrl}
        onFieldChange={actions.setFormField}
        onGenerateMapsUrl={actions.generateMapsUrl}
        onAddFranja={actions.addFranja}
        onRemoveFranja={actions.removeFranja}
        onUpdateFranja={actions.updateFranja}
        onSubmit={actions.save}
        onClose={actions.closeDrawer}
      />
    </section>
  );
}
