import { useState } from 'react';

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

export function TenantSetupWizard({ module, onTenantCreated, session, tenant, initialTab }) {
  const [activeTab, setActiveTab] = useState(initialTab || 'tenant');
  const { state, actions } = useTenantSetupData({ session, tenant, onTenantCreated, setActiveTab });
  const { notice } = state;

  return (
    <section className="module-card wizard-card">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Wizard MVP</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <div className="wizard-selected-tenant">
          <span>Tenant activo</span>
          <strong>{tenant?.label || 'Sin tenant seleccionado'}</strong>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Secciones del wizard">
        {wizardTabs.map((tab) => (
          <button
            aria-selected={activeTab === tab.id}
            className={`tab ${activeTab === tab.id ? 'active' : ''}`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

      {activeTab === 'tenant' ? <GeneralTab state={state} actions={actions} /> : null}
      {activeTab === 'calificacion' ? <QualificationTab state={state} actions={actions} session={session} /> : null}
      {activeTab === 'settings' ? <SettingsTab state={state} actions={actions} /> : null}
      {activeTab === 'hours' ? <ScheduleTab state={state} actions={actions} /> : null}
      {activeTab === 'branches' ? <BranchesTab state={state} session={session} /> : null}
      {activeTab === 'escalation' ? <EscalationTab state={state} actions={actions} /> : null}
      {activeTab === 'intenciones' ? <IntentsTab state={state} actions={actions} /> : null}
      {activeTab === 'notificaciones' ? <NotificationsTab state={state} actions={actions} session={session} /> : null}
      {activeTab === 'pagos' ? <PaymentsTab state={state} actions={actions} /> : null}
      {activeTab === 'privacy' ? <PrivacyTab state={state} actions={actions} /> : null}
      {activeTab === 'voz' ? <BotPersonalityTab state={state} actions={actions} /> : null}
      {activeTab === 'ia_rag' ? <RagTab state={state} actions={actions} /> : null}
      {activeTab === 'audit' ? <AuditTab state={state} actions={actions} /> : null}
    </section>
  );
}
