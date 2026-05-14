import { useMemo } from 'react';

import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { ServicesTable } from './components/ServicesTable.jsx';
import { ServiceFormDrawer } from './components/ServiceFormDrawer.jsx';
import { DefaultDurationPanel } from './components/DefaultDurationPanel.jsx';
import { useServicesData } from './hooks/useServicesData.js';
import { buildPreview } from './servicesData.js';
import styles from './Services.module.css';

const NOTICE_TONE = { success: 'success', error: 'danger', info: 'info', warning: 'warning' };

/**
 * UI-007.4 — Negocio · Servicios.
 *
 * Split of the legacy 868-LOC `ServiceCatalog` into a feature directory:
 * orchestrator + `useServicesData` hook (catalogue state + mutations) + pure
 * `servicesData.js` helpers + presentational panels — `ServicesTable`,
 * `ServiceReorder`, `ServiceFormDrawer` (composing `RecallSettingsPanel` and
 * `AppliesWhenBuilder`) and `DefaultDurationPanel`. Logic preserved verbatim.
 *
 * The catalogue table is gated by `services.read`; the create/edit form and the
 * default-duration panel are write surfaces gated by `services.write` (the
 * backend remains the authority — admin/owner only).
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/12 _ Negocio _ Servicios.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function Services({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useServicesData({ session, tenant });

  const previewText = useMemo(() => buildPreview(state.form, tenant), [state.form, tenant]);

  return (
    <RequirePermission permissions={permissions} capability="services.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Negocio · Catálogo"
          title={module?.label || 'Servicios'}
          description="El bot ofrece estos servicios al cliente. Cada uno controla duración, precio, instrucciones pre/post, el recall automático y las reglas de elegibilidad por calificación."
          actions={
            <label className={styles.inlineCheck}>
              <input
                type="checkbox"
                checked={state.includeInactive}
                onChange={(event) => actions.setIncludeInactive(event.target.checked)}
              />
              Mostrar inactivos
            </label>
          }
        />

        {state.notice ? (
          <AlertBanner
            tone={NOTICE_TONE[state.notice.type] || 'info'}
            title={state.notice.text}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissNotice}
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
              description="Elige un tenant activo para gestionar su catálogo de servicios."
            />
          </Card>
        ) : (
          <>
            <ServicesTable
              services={state.services}
              promotions={state.promotions}
              isBusy={state.isBusy}
              loading={state.isLoading}
              onEdit={actions.startEdit}
              onDeactivate={actions.deactivate}
              onMove={actions.move}
            />

            <RequirePermission
              permissions={permissions}
              capability="services.write"
              mode="RW"
              hidden
            >
              <DefaultDurationPanel
                defaultDuration={state.defaultDuration}
                tenantSettings={state.tenantSettings}
                isBusy={state.isBusy}
                onChange={actions.setDefaultDuration}
                onSave={actions.saveDefaultDuration}
              />
              <ServiceFormDrawer
                form={state.form}
                editingId={state.editingId}
                isBusy={state.isBusy}
                recallTemplates={state.recallTemplates}
                qualificationKeys={state.qualificationKeys}
                previewText={previewText}
                onFieldChange={(patch) => actions.setForm((current) => ({ ...current, ...patch }))}
                onSubmit={actions.submit}
                onCancel={actions.resetForm}
                onAddRule={() => actions.addRule(state.qualificationKeys[0]?.key || '')}
                onUpdateRule={actions.updateRule}
                onRemoveRule={actions.removeRule}
              />
            </RequirePermission>
          </>
        )}
      </section>
    </RequirePermission>
  );
}
