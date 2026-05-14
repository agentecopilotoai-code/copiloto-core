import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { CampaignDeliveryPanel } from './components/CampaignDeliveryPanel.jsx';
import { CampaignFormDrawer } from './components/CampaignFormDrawer.jsx';
import { CampaignsTable } from './components/CampaignsTable.jsx';
import { useCampaignsData } from './hooks/useCampaignsData.js';
import styles from './CampaignsModule.module.css';

/**
 * UI-008.2 — Campañas (Manager).
 *
 * Refactor of the legacy `CampaignsModule` (686 LOC) into a feature with an
 * orchestrator + `useCampaignsData` hook + pure `campaignsData.js` + the split
 * components: `CampaignsTable` (DataTable of campaigns with per-status row
 * actions), `CampaignFormDrawer` (the create/edit `Modal` with the saved
 * segment picker + alternative segment filters) and `CampaignDeliveryPanel`
 * (the summary + delivery metric bars + recipients preview). Campaign CRUD,
 * preview, launch and cancel — including the native launch/cancel confirms —
 * are preserved verbatim. Gated by `campaigns.write` (RW); the backend remains
 * the authority.
 *
 * Visual reference: `docs/HTML DESIGN/Manager/25 _ Campañas.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function CampaignsModule({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useCampaignsData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="campaigns.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Marketing conversacional"
          title={module?.label || 'Campañas'}
          description={
            module?.summary ||
            'Envía un template aprobado a contactos segmentados. El worker procesa los destinatarios respetando opt-out y rate limits.'
          }
          actions={
            <button
              type="button"
              className={styles.primaryButton}
              onClick={actions.startCreate}
              disabled={!state.tenantId || state.isBusy}
            >
              Nueva campaña
            </button>
          }
        />

        {state.notice ? (
          <AlertBanner
            tone={state.notice.type === 'error' ? 'danger' : 'success'}
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
              description="Elige un tenant activo para gestionar campañas."
            />
          </Card>
        ) : (
          <div className={styles.layout}>
            <CampaignsTable
              campaigns={state.campaigns}
              selectedId={state.selectedId}
              isBusy={state.isBusy}
              onSelect={actions.select}
              onEdit={actions.startEdit}
              onPreview={actions.preview}
              onLaunch={actions.launch}
              onCancel={actions.cancel}
            />
            <CampaignDeliveryPanel
              campaign={state.selectedCampaign}
              templates={state.templates}
              preview={state.preview}
            />
          </div>
        )}

        <CampaignFormDrawer
          open={state.showForm}
          formMode={state.formMode}
          form={state.form}
          templates={state.templates}
          segments={state.segments}
          availableTags={state.availableTags}
          isBusy={state.isBusy}
          onChange={actions.setForm}
          onToggleTag={actions.toggleTagInForm}
          onSubmit={actions.submit}
          onClose={actions.closeForm}
        />
      </section>
    </RequirePermission>
  );
}
