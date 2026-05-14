import { RETENTION_ANONYMIZABLE } from '../tenantSetupData.js';
import { formatJson } from '../tenantSetupTransforms.js';

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
      <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
        <label>PII policy<select value={privacyForm.mode} onChange={(event) => setPrivacyForm({ ...privacyForm, mode: event.target.value })}><option value="strict">Strict</option><option value="balanced">Balanced</option><option value="minimal">Minimal</option></select></label>
        <label>Retención PII (días)<input min="1" value={privacyForm.retentionDays} onChange={(event) => setPrivacyForm({ ...privacyForm, retentionDays: event.target.value })} type="number" /></label>
        <label className="inline-check"><input checked={privacyForm.noTrain} onChange={(event) => setPrivacyForm({ ...privacyForm, noTrain: event.target.checked })} type="checkbox" /> no_train</label>
        <label className="inline-check"><input checked={privacyForm.redactBeforeModel} onChange={(event) => setPrivacyForm({ ...privacyForm, redactBeforeModel: event.target.checked })} type="checkbox" /> Redactar antes del modelo</label>
        <label className="inline-check"><input checked={privacyForm.logRedaction} onChange={(event) => setPrivacyForm({ ...privacyForm, logRedaction: event.target.checked })} type="checkbox" /> Redactar logs</label>
        <div className="pii-builder wide">
          <strong>Reglas PII</strong>
          {Object.entries(privacyForm.rules).map(([key, value]) => (
            <label key={key}>{key}<select value={value} onChange={(event) => setPrivacyForm({ ...privacyForm, rules: { ...privacyForm.rules, [key]: event.target.value } })}><option value="allow">Allow</option><option value="mask">Mask</option><option value="redact">Redact</option></select></label>
          ))}
        </div>
        <div className="builder-preview wide"><strong>Builder resultante</strong><pre>{formatJson({ pii_policy: settingsPayload.pii_policy, no_train: settingsPayload.no_train })}</pre></div>
        <div className="form-actions"><button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar privacidad</button></div>
      </form>

      <form
        className="wizard-panel"
        data-testid="retention-policies-form"
        onSubmit={handleSaveRetention}
      >
        <h3>Retención y purgado de datos (GDPR)</h3>
        <p className="hint">
          El worker corre 1 vez al día (3am UTC) y elimina o anonimiza registros más viejos
          que el plazo configurado. <strong>audit_logs</strong> no se puede anonimizar — solo borrar — por
          requisito legal. El plazo mínimo permitido es 30 días.
        </p>
        <table className="retention-table" data-testid="retention-policies-table">
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
        <div className="form-actions">
          <button
            className="primary-action"
            disabled={isBusy || !currentTenantId}
            type="submit"
            data-testid="retention-save"
          >
            Guardar política de retención
          </button>
          <button
            className="secondary-action"
            disabled={isBusy || !currentTenantId}
            onClick={() => refreshRetention(currentTenantId)}
            type="button"
            data-testid="retention-refresh"
          >
            Refrescar preview
          </button>
        </div>
      </form>
    </>
  );
}
