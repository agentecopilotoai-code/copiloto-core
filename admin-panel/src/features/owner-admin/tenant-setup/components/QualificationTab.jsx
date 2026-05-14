import QualificationQuestionsPanel from './QualificationQuestionsPanel.jsx';

export function QualificationTab({ state, actions, session }) {
  const { currentTenantId, isBusy, notificationSettings } = state;
  const { handleSaveSettings, setNotificationSettings, setNotice } = actions;

  return (
    <div className="wizard-panel">
      <form className="form-grid" onSubmit={handleSaveSettings}>
        <label>
          Umbral VIP (presupuesto)
          <input
            type="number"
            min="0"
            step="1000"
            value={notificationSettings.vip_budget_threshold ?? 0}
            onChange={(e) =>
              setNotificationSettings({
                ...notificationSettings,
                vip_budget_threshold: Number(e.target.value) || 0,
              })
            }
          />
          <small className="hint">
            Cuando el cliente elige un rango de presupuesto con valor numérico
            ≥ este umbral, recibe la etiqueta automática "VIP". Deja en 0 para
            desactivar.
          </small>
        </label>
        <div className="form-actions">
          <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
            Guardar umbral VIP
          </button>
        </div>
      </form>
      <QualificationQuestionsPanel
        session={session}
        tenantId={currentTenantId}
        onNotice={setNotice}
      />
    </div>
  );
}
