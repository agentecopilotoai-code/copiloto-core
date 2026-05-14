import { useState } from 'react';

import { AlertBanner, Card, EmptyState, PageHeader, Tabs } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
// WebWidgetPanel is a separate channel component (not part of the UI-007.8
// WhatsApp redesign); it stays at its current path until its own UI task.
import { WebWidgetPanel } from '../../../components/modules/whatsapp/WebWidgetPanel.jsx';
import { TemplatesPanel } from './components/TemplatesPanel.jsx';
import { WhatsAppHealthPanel } from './components/WhatsAppHealthPanel.jsx';
import { WhatsAppWizardSteps } from './components/WhatsAppWizardSteps.jsx';
import { useWhatsAppData } from './hooks/useWhatsAppData.js';
import { CHANNEL_TABS } from './whatsappData.js';
import styles from './WhatsAppOnboarding.module.css';

/**
 * UI-007.8 — Canales · WhatsApp Cloud API.
 *
 * Redesign of the legacy `WhatsAppOnboarding` (801 LOC): the WhatsApp panel is
 * split into `WhatsAppWizardSteps` (channel form + onboarding checklist),
 * `WhatsAppHealthPanel` (health snapshot + identifiers) and `TemplatesPanel`
 * (semaphore + create form + list). Channel/template state and the mutation
 * handlers live in `useWhatsAppData`; logic is preserved verbatim. Gated by
 * `whatsapp.read` (the backend remains the authority).
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/16 _ Canales · WhatsApp Cloud API.html`.
 * Declared difference: the HTML's 24h message-volume KPIs and the webhook
 * delivery feed are not modelled by `getWhatsAppChannelHealth` — they are
 * deferred; no data is fabricated.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function WhatsAppOnboarding({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const [activeTab, setActiveTab] = useState('whatsapp');
  const { state, actions } = useWhatsAppData({ session, tenant });

  const tabItems = CHANNEL_TABS.map((tab) => ({ value: tab.id, label: tab.label }));

  return (
    <RequirePermission permissions={permissions} capability="whatsapp.read">
      <section className={styles.page}>
        <PageHeader
          eyebrow="IA & Canales"
          title={module?.label || 'WhatsApp'}
          description="Configuración del canal WhatsApp Cloud API: identificadores del WABA, secretos del tenant, salud del canal y plantillas aprobadas por Meta."
        />

        <Tabs items={tabItems} value={activeTab} onChange={setActiveTab} />

        {activeTab === 'web' ? (
          <WebWidgetPanel session={session} tenant={tenant} />
        ) : (
          <>
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

            {state.isLoadingChannel ? (
              <p className={styles.hint}>Cargando canal WhatsApp existente…</p>
            ) : null}

            {!state.tenantId ? (
              <Card padding="md">
                <EmptyState
                  title="Selecciona un tenant"
                  description="Elige un tenant activo para configurar su canal de WhatsApp."
                />
              </Card>
            ) : (
              <>
                <WhatsAppWizardSteps
                  form={state.form}
                  checklist={state.checklist}
                  health={state.health}
                  isBusy={state.isBusy}
                  isLoadingChannel={state.isLoadingChannel}
                  loadError={state.loadError}
                  tenantId={state.tenantId}
                  onFieldChange={actions.updateField}
                  onSubmit={actions.submitChannel}
                  onRefreshHealth={actions.refreshHealth}
                />
                <WhatsAppHealthPanel health={state.health} channel={state.channel} />
                <TemplatesPanel
                  templates={state.templates}
                  templatesByPurpose={state.templatesByPurpose}
                  templateForm={state.templateForm}
                  isLoadingTemplates={state.isLoadingTemplates}
                  isBusy={state.isBusy}
                  tenantId={state.tenantId}
                  onTemplateFormChange={actions.setTemplateForm}
                  onCreate={actions.createTemplate}
                  onSync={actions.syncTemplates}
                  onDelete={actions.deleteTemplate}
                />
              </>
            )}
          </>
        )}
      </section>
    </RequirePermission>
  );
}
