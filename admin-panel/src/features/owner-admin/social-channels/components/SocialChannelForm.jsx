import { Card, CardHeader, FormField } from '../../../../components/ui/index.js';
import { providerMeta } from '../socialChannelsData.js';
import styles from '../SocialChannelsModule.module.css';

/**
 * Create / update form for a social channel. Reuses `Card` + `FormField`.
 * Presentational — all state and the submit action come from the
 * `useSocialChannelsData` hook via props. The HMAC validation + 24h service
 * window are enforced server-side (same logic as the WhatsApp webhook).
 *
 * @param {{
 *   form: object,
 *   providerId: string,
 *   submitting: boolean,
 *   tenantId: string | undefined,
 *   onFieldChange: (patch: object) => void,
 *   onSubmit: () => void,
 * }} props
 */
export function SocialChannelForm({ form, providerId, submitting, tenantId, onFieldChange, onSubmit }) {
  const meta = providerMeta(providerId);
  const set = (key) => (event) => onFieldChange({ [key]: event.target.value });

  return (
    <Card padding="md">
      <CardHeader
        title={`Configurar ${meta?.label || 'canal'}`}
        subtitle="La validación HMAC y la ventana de 24 h reusan la misma lógica del webhook de WhatsApp."
      />
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField label={meta?.recipientLabel || 'Identificador de la cuenta'} required>
          <input
            type="text"
            required
            value={form.recipient_account_id}
            onChange={set('recipient_account_id')}
          />
        </FormField>
        <FormField label="Business ID (opcional)">
          <input type="text" value={form.business_id} onChange={set('business_id')} />
        </FormField>
        <FormField label="Page access token" hint="Se guarda como secreto del tenant; pégalo solo para crearlo o rotarlo.">
          <input
            type="password"
            autoComplete="off"
            value={form.meta_access_token}
            onChange={set('meta_access_token')}
            placeholder="EAAG..."
          />
        </FormField>
        <div className={styles.formRow}>
          <FormField label="App secret">
            <input
              type="password"
              autoComplete="off"
              value={form.app_secret}
              onChange={set('app_secret')}
            />
          </FormField>
          <FormField label="Verify token (mínimo 16 caracteres)">
            <input
              type="password"
              autoComplete="off"
              minLength={16}
              value={form.verify_token}
              onChange={set('verify_token')}
            />
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Modo">
            <select value={form.account_mode} onChange={set('account_mode')}>
              <option value="mock">mock</option>
              <option value="live">live</option>
            </select>
          </FormField>
          <FormField label="Ventana de servicio (horas)">
            <input
              type="number"
              min={1}
              max={168}
              value={form.service_window_hours}
              onChange={set('service_window_hours')}
            />
          </FormField>
        </div>
        <div className={styles.formActions}>
          <button
            type="submit"
            className={styles.primaryButton}
            disabled={submitting || !tenantId}
          >
            {submitting ? 'Guardando…' : 'Guardar canal'}
          </button>
        </div>
      </form>
    </Card>
  );
}
