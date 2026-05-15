import { Button, Card } from '../../../../components/ui/index.js';
import { ALL_INTENTS_META } from '../tenantSetupData.js';
import styles from '../TenantSetupWizard.module.css';

export function IntentsTab({ state, actions }) {
  const { intentSettings, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setIntentSettings } = actions;

  return (
    <Card padding="md">
      <form onSubmit={handleSaveSettings}>
        <p className={styles.hint}>
          Habilita o deshabilita intenciones por tenant y agrega keywords personalizadas adicionales
          a las globales del sistema. El umbral de confianza mínima controla cuándo el bot escala
          al agente humano por incertidumbre.
        </p>

        <fieldset className={styles.fieldset}>
          <legend>Umbral de confianza mínima</legend>
          <label className={styles.inlineCheck}>
            <input
              type="range"
              min="0.50"
              max="0.90"
              step="0.01"
              value={intentSettings.min_confidence}
              onChange={(e) =>
                setIntentSettings({ ...intentSettings, min_confidence: Number(e.target.value) })
              }
            />
            <span className="status-badge active">{intentSettings.min_confidence.toFixed(2)}</span>
          </label>
          <p className={styles.hint}>
            Rango 0.50–0.90 · default 0.70. Por debajo de este valor el bot escala al agente.
          </p>
        </fieldset>

        <div className={styles.intentList}>
          {ALL_INTENTS_META.map((meta) => {
            const enabled = intentSettings.enabled_intents.includes(meta.id);
            const kws = (intentSettings.custom_keywords[meta.id] || []).join(', ');
            return (
              <fieldset key={meta.id} className={styles.fieldset}>
                <legend>
                  <label className={styles.inlineCheck}>
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
                    <code>{meta.id}</code>
                  </label>
                </legend>
                <p className={styles.hint}>{meta.description}</p>
                {enabled && (
                  <label className={styles.inlineCheck}>
                    Keywords personalizadas (comma-separated)
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
                    />
                  </label>
                )}
              </fieldset>
            );
          })}
        </div>

        <div className={styles.actions}>
          <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
            Guardar intenciones
          </Button>
        </div>
      </form>
    </Card>
  );
}
