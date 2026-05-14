import { Card, CardHeader, FormField } from '../../../../components/ui/index.js';
import styles from '../Services.module.css';

/**
 * Tenant-level fallback duration panel: the default appointment duration used
 * when a service has no duration of its own. Persists into
 * `escalation_policy.service_durations.default` via the data hook.
 *
 * @param {{
 *   defaultDuration: number|string,
 *   tenantSettings: object|null,
 *   isBusy: boolean,
 *   onChange: (value: string) => void,
 *   onSave: () => void,
 * }} props
 */
export function DefaultDurationPanel({ defaultDuration, tenantSettings, isBusy, onChange, onSave }) {
  return (
    <Card padding="md">
      <CardHeader
        title="Duración por defecto"
        subtitle="Se usa cuando no hay catálogo o el servicio no tiene duración propia"
      />
      <form
        className={styles.inlineForm}
        onSubmit={(event) => {
          event.preventDefault();
          onSave();
        }}
      >
        <FormField label="Duración por defecto (minutos)">
          <input
            type="number"
            min="1"
            max="1440"
            value={defaultDuration}
            disabled={!tenantSettings}
            onChange={(event) => onChange(event.target.value)}
          />
        </FormField>
        <button
          type="submit"
          className={styles.secondaryButton}
          disabled={isBusy || !tenantSettings}
        >
          Guardar fallback
        </button>
      </form>
    </Card>
  );
}
