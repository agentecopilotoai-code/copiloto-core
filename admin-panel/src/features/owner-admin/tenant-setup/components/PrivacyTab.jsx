import { Button, Card, FormField } from '../../../../components/ui/index.js';
import { RETENTION_ANONYMIZABLE } from '../tenantSetupData.js';
import { formatJson } from '../tenantSetupTransforms.js';
import styles from '../TenantSetupWizard.module.css';

export function PrivacyTab({ state, actions }) {
  const {
    privacyForm,
    settingsPayload,
    isBusy,
    currentTenantId,
    retentionPolicies,
    retentionPreview,
  } = state;
  const {
    handleSaveSettings,
    setPrivacyForm,
    handleSaveRetention,
    updateRetentionRow,
    refreshRetention,
  } = actions;

  return (
    <>
      <Card padding="md">
        <form className={styles.formGrid} onSubmit={handleSaveSettings}>
          <FormField label="PII policy">
            <select
              value={privacyForm.mode}
              onChange={(event) => setPrivacyForm({ ...privacyForm, mode: event.target.value })}
            >
              <option value="strict">Strict</option>
              <option value="balanced">Balanced</option>
              <option value="minimal">Minimal</option>
            </select>
          </FormField>
          <FormField label="Retención PII (días)">
            <input
              min="1"
              value={privacyForm.retentionDays}
              onChange={(event) => setPrivacyForm({ ...privacyForm, retentionDays: event.target.value })}
              type="number"
            />
          </FormField>
          <label className={styles.inlineCheck}>
            <input
              checked={privacyForm.noTrain}
              onChange={(event) => setPrivacyForm({ ...privacyForm, noTrain: event.target.checked })}
              type="checkbox"
            />
            no_train
          </label>
          <label className={styles.inlineCheck}>
            <input
              checked={privacyForm.redactBeforeModel}
              onChange={(event) => setPrivacyForm({ ...privacyForm, redactBeforeModel: event.target.checked })}
              type="checkbox"
            />
            Redactar antes del modelo
          </label>
          <label className={styles.inlineCheck}>
            <input
              checked={privacyForm.logRedaction}
              onChange={(event) => setPrivacyForm({ ...privacyForm, logRedaction: event.target.checked })}
              type="checkbox"
            />
            Redactar logs
          </label>
          <fieldset className={`${styles.fieldset} ${styles.wide}`}>
            <legend>Reglas PII</legend>
            <div className={styles.formGrid}>
              {Object.entries(privacyForm.rules).map(([key, value]) => (
                <FormField key={key} label={key}>
                  <select
                    value={value}
                    onChange={(event) => setPrivacyForm({
                      ...privacyForm,
                      rules: { ...privacyForm.rules, [key]: event.target.value },
                    })}
                  >
                    <option value="allow">Allow</option>
                    <option value="mask">Mask</option>
                    <option value="redact">Redact</option>
                  </select>
                </FormField>
              ))}
            </div>
          </fieldset>
          <div className={`${styles.builderPreview} ${styles.wide}`}>
            <strong>Builder resultante</strong>
            <pre>{formatJson({ pii_policy: settingsPayload.pii_policy, no_train: settingsPayload.no_train })}</pre>
          </div>
          <div className={styles.actions}>
            <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
              Guardar privacidad
            </Button>
          </div>
        </form>
      </Card>

      <Card padding="md">
        <form data-testid="retention-policies-form" onSubmit={handleSaveRetention}>
          <h3 className={styles.sectionTitle}>Retención y purgado de datos (GDPR)</h3>
          <p className={styles.hint}>
            El worker corre 1 vez al día (3am UTC) y elimina o anonimiza registros más viejos
            que el plazo configurado. <strong>audit_logs</strong> no se puede anonimizar — solo borrar — por
            requisito legal. El plazo mínimo permitido es 30 días.
          </p>
          <table className={styles.retentionTable} data-testid="retention-policies-table">
            <thead>
              <tr>
                <th>Entidad</th>
                <th>Días de retención</th>
                <th>Anonimizar (en vez de borrar)</th>
                <th>Se purgarán mañana</th>
                <th>Total actual</th>
              </tr>
            </thead>
            <tbody>
              {retentionPolicies.map((row) => {
                const preview = retentionPreview.find((p) => p.entity === row.entity) || {};
                return (
                  <tr key={row.entity} data-testid={`retention-row-${row.entity}`}>
                    <td>{row.entity}</td>
                    <td>
                      <input
                        type="number"
                        min="30"
                        value={row.retention_days}
                        onChange={(event) =>
                          updateRetentionRow(row.entity, { retention_days: event.target.value })
                        }
                        data-testid={`retention-days-${row.entity}`}
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={Boolean(row.anonymize_instead_of_delete)}
                        disabled={!RETENTION_ANONYMIZABLE.has(row.entity)}
                        onChange={(event) =>
                          updateRetentionRow(row.entity, {
                            anonymize_instead_of_delete: event.target.checked,
                          })
                        }
                        data-testid={`retention-anon-${row.entity}`}
                      />
                    </td>
                    <td data-testid={`retention-candidates-${row.entity}`}>
                      {preview.candidates ?? '—'}
                    </td>
                    <td>{preview.total ?? '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className={styles.actions}>
            <Button
              variant="primary"
              disabled={isBusy || !currentTenantId}
              type="submit"
              data-testid="retention-save"
            >
              Guardar política de retención
            </Button>
            <Button
              variant="secondary"
              disabled={isBusy || !currentTenantId}
              onClick={() => refreshRetention(currentTenantId)}
              type="button"
              data-testid="retention-refresh"
            >
              Refrescar preview
            </Button>
          </div>
        </form>
      </Card>
    </>
  );
}
