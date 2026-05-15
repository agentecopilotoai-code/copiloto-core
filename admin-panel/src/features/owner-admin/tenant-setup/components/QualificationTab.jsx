import { Button, Card, FormField } from '../../../../components/ui/index.js';
import QualificationQuestionsPanel from './QualificationQuestionsPanel.jsx';
import styles from '../TenantSetupWizard.module.css';

export function QualificationTab({ state, actions, session }) {
  const { currentTenantId, isBusy, notificationSettings } = state;
  const { handleSaveSettings, setNotificationSettings, setNotice } = actions;

  return (
    <Card padding="md">
      <form className={styles.formGrid} onSubmit={handleSaveSettings}>
        <FormField
          label="Umbral VIP (presupuesto)"
          hint='Cuando el cliente elige un rango de presupuesto con valor numérico ≥ este umbral, recibe la etiqueta automática "VIP". Deja en 0 para desactivar.'
        >
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
        </FormField>
        <div className={styles.actions}>
          <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
            Guardar umbral VIP
          </Button>
        </div>
      </form>
      <QualificationQuestionsPanel
        session={session}
        tenantId={currentTenantId}
        onNotice={setNotice}
      />
    </Card>
  );
}
