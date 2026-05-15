import { Button, Card, FormField } from '../../../../components/ui/index.js';
import { COUNTRY_PROFILES, SUPPORTED_COUNTRIES } from '../tenantSetupData.js';
import { formatJson } from '../tenantSetupTransforms.js';
import styles from '../TenantSetupWizard.module.css';

export function SettingsTab({ state, actions }) {
  const { settingsForm, settingsPayload, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setSettingsForm } = actions;

  return (
    <Card padding="md">
      <form className={styles.formGrid} onSubmit={handleSaveSettings}>
        {/* TASK-0073: el locale se elige del catálogo ``es-XX`` soportado. */}
        <FormField label="Locale del tenant">
          <select
            value={settingsForm.locale}
            onChange={(event) => setSettingsForm({ locale: event.target.value })}
            required
          >
            {SUPPORTED_COUNTRIES.map((code) => (
              <option key={code} value={COUNTRY_PROFILES[code].locale}>
                {COUNTRY_PROFILES[code].locale} — {COUNTRY_PROFILES[code].label}
              </option>
            ))}
          </select>
        </FormField>
        <div className={`${styles.builderPreview} ${styles.wide}`}>
          <strong>Payload construido por el formulario</strong>
          <pre>{formatJson({ locale: settingsPayload.locale })}</pre>
        </div>
        <div className={styles.actions}>
          <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
            Guardar configuración completa
          </Button>
        </div>
      </form>
    </Card>
  );
}
