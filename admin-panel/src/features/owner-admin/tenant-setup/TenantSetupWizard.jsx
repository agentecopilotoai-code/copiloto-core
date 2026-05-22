import { useState } from 'react';

import { Card, PageHeader, Tabs } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';

import { wizardTabs } from './tenantSetupData.js';
import { useTenantSetupData } from './hooks/useTenantSetupData.js';
import { GeneralTab } from './components/GeneralTab.jsx';
import { QualificationTab } from './components/QualificationTab.jsx';
import { SettingsTab } from './components/SettingsTab.jsx';
import { ScheduleTab } from './components/ScheduleTab.jsx';
import { BranchesTab } from './components/BranchesTab.jsx';
import { EscalationTab } from './components/EscalationTab.jsx';
import { IntentsTab } from './components/IntentsTab.jsx';
import { NotificationsTab } from './components/NotificationsTab.jsx';
import { PaymentsTab } from './components/PaymentsTab.jsx';
import { PrivacyTab } from './components/PrivacyTab.jsx';
import { BotPersonalityTab } from './components/BotPersonalityTab.jsx';
import { RagTab } from './components/RagTab.jsx';
import { AuditTab } from './components/AuditTab.jsx';
import styles from './TenantSetupWizard.module.css';

/**
 * UI-021 — Tenant Setup Wizard (Owner / Admin · Config).
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/20 _ Config _ Tenant Setup
 * _ Voz del bot.html`. Replaces the legacy "Wizard MVP" header + ad-hoc
 * `<button className="primary-action">` blocks with the design-system
 * primitives (`<PageHeader>`, `<Card>`, `<Tabs>`, `<Button>`, `<FormField>`).
 * Behaviour and data flow (the `useTenantSetupData` hook, every subtab from
 * UI-007.12) are preserved verbatim — this PR is visual-only.
 *
 * The wizard is gated by `tenant_setup.write` (RW) at the entry point WHEN
 * an existing tenant is being edited; the registry has `capability: null` so
 * the wrapper here is the authority on the client. The backend remains the
 * source of truth.
 *
 * `initialSignup={true}` SKIPS the gate — this is the entry from
 * `/onboarding` (router.jsx OnboardingRoute), where the user has NO tenant
 * yet and therefore has no roles in any tenant. Without this exception the
 * first-time signup user would crash into `<AccessDenied>` and have no path
 * forward. (BUG-002 fix.)
 *
 * @param {{ module: object, session: object, tenant?: object, initialTab?: string,
 *           initialSignup?: boolean, onTenantCreated?: Function }} props
 */
// BUG-080: outer component que GATEA por permisos ANTES de montar el body
// que dispara `useTenantSetupData` (que fetches tenant/settings/tags/payments
// en mount). Sin esta separación, viewers/agents sin `tenant_setup.write`
// generaban TODAS las network calls antes de ver el AccessDenied.
export function TenantSetupWizard(props) {
  const { tenant, initialSignup = false } = props;
  const { profile } = useTenantContext();
  const permissions = usePermissions();

  // Signup inicial bypassa permission check — el caller (anon o sin tenant)
  // no tiene roles aún; el backend tiene su propio gate en /v1/tenant-signup.
  if (initialSignup) {
    return <TenantSetupWizardBody {...props} />;
  }

  return (
    <RequirePermission permissions={permissions} capability="tenant_setup.write" mode="RW">
      <TenantSetupWizardBody {...props} />
    </RequirePermission>
  );
}

function TenantSetupWizardBody({ module, onTenantCreated, session, tenant, initialTab, initialSignup = false }) {
  // `initialSignup` se usa para el label "Nuevo tenant" abajo. El gate
  // de permisos lo hace el outer TenantSetupWizard.
  const [activeTab, setActiveTab] = useState(initialTab || 'tenant');
  const { state, actions } = useTenantSetupData({ session, tenant, onTenantCreated, setActiveTab });
  const { notice } = state;

  const noticeClass = notice
    ? [
        styles.notice,
        notice.type === 'success' ? styles['notice--success'] : '',
        notice.type === 'error' ? styles['notice--error'] : '',
        notice.type !== 'success' && notice.type !== 'error' ? styles['notice--info'] : '',
      ]
        .filter(Boolean)
        .join(' ')
    : '';

  const panel = renderPanel({ activeTab, state, actions, session });

  const wizard = (
    <section className={styles.page}>
      <PageHeader
        eyebrow="Configuración"
        title={module?.label || 'Tenant Setup'}
        description={module?.summary || 'Configuración general del tenant.'}
        actions={
          <div className={styles.tenantMeta}>
            <span>Tenant activo</span>
            <strong>{tenant?.label || (initialSignup ? 'Nuevo tenant' : 'Sin tenant seleccionado')}</strong>
          </div>
        }
      />

      <Tabs
        items={wizardTabs.map((tab) => ({ value: tab.id, label: tab.label }))}
        value={activeTab}
        onChange={setActiveTab}
        variant="underline"
      />

      {notice ? (
        <p className={noticeClass} role="status">
          {notice.text}
        </p>
      ) : null}

      {panel}
    </section>
  );

  return wizard;
}

function renderPanel({ activeTab, state, actions, session }) {
  switch (activeTab) {
    case 'tenant':
      return <GeneralTab state={state} actions={actions} />;
    case 'calificacion':
      return <QualificationTab state={state} actions={actions} session={session} />;
    case 'settings':
      return <SettingsTab state={state} actions={actions} />;
    case 'hours':
      return <ScheduleTab state={state} actions={actions} />;
    case 'branches':
      return <BranchesTab state={state} session={session} />;
    case 'escalation':
      return <EscalationTab state={state} actions={actions} />;
    case 'intenciones':
      return <IntentsTab state={state} actions={actions} />;
    case 'notificaciones':
      return <NotificationsTab state={state} actions={actions} session={session} />;
    case 'pagos':
      return <PaymentsTab state={state} actions={actions} />;
    case 'privacy':
      return <PrivacyTab state={state} actions={actions} />;
    case 'voz':
      return <BotPersonalityTab state={state} actions={actions} />;
    case 'ia_rag':
      return <RagTab state={state} actions={actions} />;
    case 'audit':
      return <AuditTab state={state} actions={actions} />;
    default:
      return null;
  }
}
