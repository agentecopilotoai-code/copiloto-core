export function ComplaintAlertChannelsFieldset({ notificationSettings, setNotificationSettings }) {
  return (
    <fieldset className="wide" data-wizard-field="complaint_alert_channels" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
      <legend>Alertas al equipo (TASK-0057)</legend>
      <p className="hint" style={{ marginTop: 0 }}>
        Cuando un cliente deja 1–2★ o una queja, avisamos al equipo por estos canales.
        Configura al menos uno para no depender de que alguien esté mirando el Desk.
        WhatsApp al manager es el más rápido.
      </p>
      <label className="wide">
        Emails (separados por coma)
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
      </label>
      <label className="wide">
        WhatsApps (E.164, separados por coma)
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
      </label>
      <label className="wide">
        Webhook (URL HTTPS, opcional)
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
      </label>
      <p className="hint" style={{ marginTop: '0.25rem' }}>
        Solo URLs HTTPS públicas. Loopback, RFC1918, link-local y
        metadata cloud (169.254.169.254, metadata.google.internal) son
        rechazados con 422.
        El webhook se firma con HMAC SHA256 si existe el archivo
        <code> .secrets/tenants/&lt;tenant_id&gt;/alerts_webhook_secret</code>.
        El template de WhatsApp <code>complaint_alert_v1</code> debe estar aprobado
        en Meta para que la alerta salga.
      </p>
    </fieldset>
  );
}
