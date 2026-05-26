import { Button, Card, FormField } from '../../../../components/ui/index.js';
import { ComplaintAlertChannelsFieldset } from './ComplaintAlertChannelsFieldset.jsx';
// Branch `core`: DigestSubscriptionsPanel removido (módulo manager chatbot).
import styles from '../TenantSetupWizard.module.css';

export function NotificationsTab({ state, actions, session }) {
  const { notificationSettings, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setNotificationSettings } = actions;
  const set = (patch) => setNotificationSettings({ ...notificationSettings, ...patch });

  const previewMessage =
    `Hola {nombre},\n\nTu cita de {servicio} quedó agendada para el {fecha} a las {hora}` +
    (notificationSettings.include_location_link && notificationSettings.location_address
      ? `\n\n📍 ${notificationSettings.location_address}`
      : '') +
    (notificationSettings.include_location_link && notificationSettings.location_maps_url
      ? `\n${notificationSettings.location_maps_url}`
      : '') +
    (notificationSettings.include_preparation_notes
      ? '\n\n📋 Instrucciones de preparación (del catálogo del servicio).'
      : '');

  return (
    <Card padding="md">
      <form className={styles.formGrid} onSubmit={handleSaveSettings}>
        <p className={`${styles.hint} ${styles.wide}`}>
          Configura qué recordatorios y mensajes post-cita se envían por WhatsApp.
          Cada notificación requiere una plantilla aprobada con el mismo propósito en
          la pestaña <em>Plantillas de mensajes</em> del módulo WhatsApp.
        </p>

        <fieldset className={`${styles.fieldset} ${styles.wide}`}>
          <legend>Confirmación y recordatorios</legend>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.confirmation_enabled}
              onChange={(e) => set({ confirmation_enabled: e.target.checked })}
            />
            Enviar confirmación inmediata al crear la cita
          </label>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.reminder_24h_enabled}
              onChange={(e) => set({ reminder_24h_enabled: e.target.checked })}
            />
            Recordatorio 24 horas antes
          </label>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.reminder_1h_enabled}
              onChange={(e) => set({ reminder_1h_enabled: e.target.checked })}
            />
            Recordatorio 1 hora antes
          </label>
        </fieldset>

        <fieldset className={`${styles.fieldset} ${styles.wide}`}>
          <legend>Ubicación e instrucciones</legend>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.include_location_link}
              onChange={(e) => set({ include_location_link: e.target.checked })}
            />
            Incluir ubicación en los mensajes
          </label>
          <FormField label="Dirección">
            <input
              value={notificationSettings.location_address}
              onChange={(e) => set({ location_address: e.target.value })}
              placeholder="Cra. 7 #45-23, Bogotá"
            />
          </FormField>
          <FormField label="URL de Google Maps">
            <input
              value={notificationSettings.location_maps_url}
              onChange={(e) => set({ location_maps_url: e.target.value })}
              placeholder="https://maps.google.com/?q=..."
            />
          </FormField>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.include_preparation_notes}
              onChange={(e) => set({ include_preparation_notes: e.target.checked })}
            />
            Incluir instrucciones de preparación del servicio
          </label>
        </fieldset>

        <fieldset className={`${styles.fieldset} ${styles.wide}`}>
          <legend>Reducción de no-show</legend>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.no_show_confirmation_enabled}
              onChange={(e) => set({ no_show_confirmation_enabled: e.target.checked })}
            />
            Enviar confirmación activa antes de la cita
          </label>
          <FormField label="Horas antes de la cita">
            <input
              type="number"
              min="1"
              max="48"
              value={notificationSettings.confirmation_reminder_hours}
              onChange={(e) => set({ confirmation_reminder_hours: Number(e.target.value) || 0 })}
            />
          </FormField>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.auto_rebook_on_decline !== false}
              onChange={(e) => set({ auto_rebook_on_decline: e.target.checked })}
            />
            Ofrecer reprogramar al declinar la confirmación
          </label>
          <p className={styles.hint}>
            Si el cliente responde "no" al pedido de confirmación activa, el bot ofrecerá tres
            horarios alternativos en lugar de quedarse esperando a un agente. Si responde "no"
            al rebooking, la cita se cancela y se escala al equipo.
          </p>
          <FormField label="Tiempo máximo del auto-rebook (min)">
            <input
              type="number"
              min="10"
              max="240"
              value={notificationSettings.auto_rebook_timeout_minutes ?? 90}
              onChange={(e) => set({ auto_rebook_timeout_minutes: Number(e.target.value) || 0 })}
            />
          </FormField>
          <p className={styles.hint}>
            Si el cliente recibe los horarios y no responde dentro de esta ventana, la cita se
            cancela y la conversación se escala con la etiqueta "Necesita seguimiento".
            Rango 10–240 min, por defecto 90.
          </p>
          <label className={styles.inlineCheck} data-wizard-field="ask_referrer">
            <input
              type="checkbox"
              checked={notificationSettings.ask_referrer === true}
              onChange={(e) => set({ ask_referrer: e.target.checked })}
            />
            Preguntar "¿quién te recomendó?" al iniciar el booking
          </label>
          <p className={styles.hint}>
            Captura al embajador para medir referidos en Analítica → Top
            referidores. Default desactivado.
          </p>
        </fieldset>

        <ComplaintAlertChannelsFieldset
          notificationSettings={notificationSettings}
          setNotificationSettings={setNotificationSettings}
        />

        {/* Branch `core`: panel de suscripciones a digest removido (módulo chatbot). */}

        <fieldset className={`${styles.fieldset} ${styles.wide}`}>
          <legend>Flujo post-cita</legend>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.post_instructions_enabled}
              onChange={(e) => set({ post_instructions_enabled: e.target.checked })}
            />
            Enviar instrucciones post-servicio
          </label>
          <FormField label="Minutos después del final">
            <input
              type="number"
              min="0"
              max="1440"
              value={notificationSettings.post_instructions_delay_minutes}
              onChange={(e) => set({ post_instructions_delay_minutes: Number(e.target.value) || 0 })}
            />
          </FormField>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.post_feedback_enabled}
              onChange={(e) => set({ post_feedback_enabled: e.target.checked })}
            />
            Pedir feedback al cliente (1–5)
          </label>
          <FormField label="Horas después del final">
            <input
              type="number"
              min="0"
              max="168"
              value={notificationSettings.post_feedback_delay_hours}
              onChange={(e) => set({ post_feedback_delay_hours: Number(e.target.value) || 0 })}
            />
          </FormField>
          <label className={styles.inlineCheck}>
            <input
              type="checkbox"
              checked={notificationSettings.post_rebooking_enabled}
              onChange={(e) => set({ post_rebooking_enabled: e.target.checked })}
            />
            Invitar a nueva cita
          </label>
          <FormField label="Días después">
            <input
              type="number"
              min="1"
              max="365"
              value={notificationSettings.post_rebooking_delay_days}
              onChange={(e) => set({ post_rebooking_delay_days: Number(e.target.value) || 0 })}
            />
          </FormField>
          <FormField label="Mensaje personalizado de rebooking">
            <textarea
              rows={2}
              value={notificationSettings.post_rebooking_message}
              onChange={(e) => set({ post_rebooking_message: e.target.value })}
              placeholder="Hola {{1}}, ya pasó un tiempo desde tu última visita. ¿Te gustaría agendar?"
            />
          </FormField>
        </fieldset>

        <div className={`${styles.builderPreview} ${styles.wide}`}>
          <strong>Preview del mensaje de confirmación</strong>
          <pre>{previewMessage}</pre>
        </div>

        <div className={styles.actions}>
          <Button variant="primary" disabled={isBusy || !currentTenantId} type="submit">
            Guardar notificaciones
          </Button>
        </div>
      </form>
    </Card>
  );
}
