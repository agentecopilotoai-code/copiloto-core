import { AlertBanner, Card, EmptyState, PageHeader, Tabs } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { SocialChannelForm } from './components/SocialChannelForm.jsx';
import { SocialChannelStatus } from './components/SocialChannelStatus.jsx';
import { useSocialChannelsData } from './hooks/useSocialChannelsData.js';
import { PROVIDER_OPTIONS } from './socialChannelsData.js';
import styles from './SocialChannelsModule.module.css';

/**
 * UI-007.9 — Canales · Instagram / Messenger.
 *
 * Refactor of the legacy `SocialChannelsModule` (265 LOC) into a feature with
 * an orchestrator + `useSocialChannelsData` hook + pure `socialChannelsData.js`
 * + `SocialChannelStatus` / `SocialChannelForm` panels, reusing the same UI
 * primitives as the UI-007.8 WhatsApp redesign. Channel state + the upsert
 * handler are preserved verbatim. Gated by `social_channels.write` (RW); the
 * backend remains the authority.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/17 _ Canales · Instagram · Messenger.html`.
 * Declared difference: the HTML's 24h traffic KPIs, the subscribed-events list
 * and the recent-messages feed are not modelled by `listMessengerChannels` —
 * they are deferred; no data is fabricated.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function SocialChannelsModule({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, actions } = useSocialChannelsData({ session, tenant });

  const tabItems = PROVIDER_OPTIONS.map((opt) => ({ value: opt.id, label: opt.label }));

  return (
    <RequirePermission permissions={permissions} capability="social_channels.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="IA & Canales"
          title={module?.label || 'Redes sociales'}
          description="Misma orquestación que WhatsApp: el bot atiende DMs de Instagram y Messenger con la misma cascada RAG → policy engine → handoff. La ventana de servicio de 24 h se aplica en el outbound worker."
        />

        <Tabs items={tabItems} value={state.activeProvider} onChange={actions.setActiveProvider} />

        {state.error ? <AlertBanner tone="danger" title={state.error} /> : null}
        {state.loading ? <p className={styles.hint}>Cargando canales…</p> : null}

        {state.feedback ? (
          <AlertBanner
            tone={state.feedback.kind === 'ok' ? 'success' : 'danger'}
            title={state.feedback.text}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissFeedback}
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
              description="Elige un tenant activo para configurar sus canales sociales."
            />
          </Card>
        ) : (
          <div className={styles.layout}>
            <SocialChannelStatus channel={state.currentChannel} providerId={state.activeProvider} />
            <SocialChannelForm
              form={state.form}
              providerId={state.activeProvider}
              submitting={state.submitting}
              tenantId={state.tenantId}
              onFieldChange={actions.setFormField}
              onSubmit={actions.submit}
            />
          </div>
        )}
      </section>
    </RequirePermission>
  );
}
