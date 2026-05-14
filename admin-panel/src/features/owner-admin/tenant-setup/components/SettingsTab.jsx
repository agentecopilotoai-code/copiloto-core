import { COUNTRY_PROFILES, SUPPORTED_COUNTRIES } from '../tenantSetupData.js';
import { formatJson } from '../tenantSetupTransforms.js';

export function SettingsTab({ state, actions }) {
  const { settingsForm, settingsPayload, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setSettingsForm } = actions;

  return (
    <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
      <label>
        Locale del tenant
        {/* TASK-0073: el locale se elige del catálogo ``es-XX`` soportado. */}
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
      </label>
      <div className="builder-preview">
        <strong>Payload construido por el formulario</strong>
        <pre>{formatJson({ locale: settingsPayload.locale })}</pre>
      </div>
      <div className="form-actions">
        <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar configuración completa</button>
      </div>
    </form>
  );
}
