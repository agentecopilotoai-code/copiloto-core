import { FormField } from '../../../../components/ui/index.js';
import styles from '../TenantSetupWizard.module.css';

export function ComplaintAlertChannelsFieldset({ notificationSettings, setNotificationSettings }) {
  return (
    <fieldset
      className={`${styles.fieldset} ${styles.wide}`}
      data-wizard-field="complaint_alert_channels"
    >
      <legend>Alertas al equipo</legend>
      <p className={styles.hint}>
        Cuando un cliente deja 1–2★ o una queja, avisamos al equipo por estos canales.
        Configura al menos uno para no depender de que alguien esté mirando el Desk.
        WhatsApp al manager es el más rápido.
      </p>
      <FormField label="Emails (separados por coma)">
        <input
          type="text"
          placeholder="manager@empresa.com, dueno@empresa.com"
          value={(notificationSettings.complaint_alert_channels?.email || []).join(', ')}
          onChange={(e) => setNotificationSettings({
            ...notificationSettings,
            complaint_alert_channels: {
              ...notificationSettings.complaint_alert_channels,
              email: e.target.value
                .split(',')
                .map((value) => value.trim())
                .filter(Boolean),
            },
          })}
        />
      </FormField>
      <FormField label="WhatsApps (E.164, separados por coma)">
        <input
          type="text"
          placeholder="+573001234567, +573009876543"
          value={(notificationSettings.complaint_alert_channels?.whatsapp || []).join(', ')}
          onChange={(e) => setNotificationSettings({
            ...notificationSettings,
            complaint_alert_channels: {
              ...notificationSettings.complaint_alert_channels,
              whatsapp: e.target.value
                .split(',')
                .map((value) => value.trim())
                .filter(Boolean),
            },
          })}
        />
      </FormField>
      <FormField label="Webhook (URL HTTPS, opcional)">
        <input
          type="url"
          placeholder="https://hooks.empresa.com/alerts/copilotoia"
          value={notificationSettings.complaint_alert_channels?.webhook_url || ''}
          onChange={(e) => setNotificationSettings({
            ...notificationSettings,
            complaint_alert_channels: {
              ...notificationSettings.complaint_alert_channels,
              webhook_url: e.target.value,
            },
          })}
        />
      </FormField>
      <p className={styles.hint}>
        Usá una URL pública con HTTPS (las direcciones internas no funcionan).
        Las alertas por WhatsApp requieren que la plantilla esté aprobada por
        Meta — si todavía no está, contactá a soporte.
      </p>
    </fieldset>
  );
}
