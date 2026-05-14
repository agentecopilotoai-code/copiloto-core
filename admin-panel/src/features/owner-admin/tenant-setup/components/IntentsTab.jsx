import { ALL_INTENTS_META } from '../tenantSetupData.js';

export function IntentsTab({ state, actions }) {
  const { intentSettings, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setIntentSettings } = actions;

  return (
    <form className="wizard-panel" onSubmit={handleSaveSettings}>
      <p className="hint" style={{ marginBottom: '1rem' }}>
        Habilita o deshabilita intenciones por tenant y agrega keywords personalizadas adicionales
        a las globales del sistema. El umbral de confianza mínima controla cuándo el bot escala
        al agente humano por incertidumbre.
      </p>

      <div style={{ marginBottom: '1.25rem' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <strong>Umbral de confianza mínima</strong>
          <input
            type="range"
            min="0.50"
            max="0.90"
            step="0.01"
            value={intentSettings.min_confidence}
            onChange={(e) => setIntentSettings({ ...intentSettings, min_confidence: Number(e.target.value) })}
            style={{ flex: 1 }}
          />
          <span className="status-badge active">{intentSettings.min_confidence.toFixed(2)}</span>
        </label>
        <p className="hint">Rango 0.50–0.90 · default 0.70. Por debajo de este valor el bot escala al agente.</p>
      </div>

      <div className="intent-list">
        {ALL_INTENTS_META.map((meta) => {
          const enabled = intentSettings.enabled_intents.includes(meta.id);
          const kws = (intentSettings.custom_keywords[meta.id] || []).join(', ');
          return (
            <fieldset key={meta.id} className="intent-card" style={{ border: '1px solid var(--border)', borderRadius: '6px', padding: '0.75rem 1rem', marginBottom: '0.5rem' }}>
              <legend style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...intentSettings.enabled_intents, meta.id]
                      : intentSettings.enabled_intents.filter((i) => i !== meta.id);
                    setIntentSettings({ ...intentSettings, enabled_intents: next });
                  }}
                />
                <strong>{meta.label}</strong>
                <code style={{ fontSize: '0.75rem', opacity: 0.7 }}>{meta.id}</code>
              </legend>
              <p className="hint" style={{ margin: '0.25rem 0 0.5rem' }}>{meta.description}</p>
              {enabled && (
                <label style={{ display: 'block' }}>
                  <span style={{ fontSize: '0.8rem' }}>Keywords personalizadas (comma-separated)</span>
                  <input
                    type="text"
                    placeholder="ej: reservar, quiero hora"
                    value={kws}
                    onChange={(e) => {
                      const list = e.target.value.split(',').map((k) => k.trim()).filter(Boolean);
                      setIntentSettings({
                        ...intentSettings,
                        custom_keywords: { ...intentSettings.custom_keywords, [meta.id]: list },
                      });
                    }}
                    style={{ width: '100%', marginTop: '0.25rem' }}
                  />
                </label>
              )}
            </fieldset>
          );
        })}
      </div>

      <div className="form-actions">
        <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
          Guardar intenciones
        </button>
      </div>
    </form>
  );
}
