import { ComplaintAlertChannelsFieldset } from './ComplaintAlertChannelsFieldset.jsx';
import DigestSubscriptionsPanel from '../../../manager/digest-reports/components/DigestSubscriptionsPanel.jsx';

export function NotificationsTab({ state, actions, session }) {
  const { notificationSettings, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setNotificationSettings } = actions;

  return (
    <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
      <p className="hint wide" style={{ marginBottom: '0.5rem' }}>
        Configura qué recordatorios y mensajes post-cita se envían por WhatsApp.
        Cada notificación requiere una plantilla aprobada con el mismo propósito en
        la pestaña <em>Plantillas de mensajes</em> del módulo WhatsApp.
      </p>

      <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
        <legend>Confirmación y recordatorios (TASK-0035)</legend>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.confirmation_enabled}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, confirmation_enabled: e.target.checked })}
          />
          Enviar confirmación inmediata al crear la cita
        </label>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.reminder_24h_enabled}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, reminder_24h_enabled: e.target.checked })}
          />
          Recordatorio 24 horas antes
        </label>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.reminder_1h_enabled}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, reminder_1h_enabled: e.target.checked })}
          />
          Recordatorio 1 hora antes
        </label>
      </fieldset>

      <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
        <legend>Ubicación e instrucciones</legend>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.include_location_link}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, include_location_link: e.target.checked })}
          />
          Incluir ubicación en los mensajes
        </label>
        <label className="wide">
          Dirección
          <input
            value={notificationSettings.location_address}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, location_address: e.target.value })}
            placeholder="Cra. 7 #45-23, Bogotá"
          />
        </label>
        <label className="wide">
          URL de Google Maps
          <input
            value={notificationSettings.location_maps_url}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, location_maps_url: e.target.value })}
            placeholder="https://maps.google.com/?q=..."
          />
        </label>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.include_preparation_notes}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, include_preparation_notes: e.target.checked })}
          />
          Incluir instrucciones de preparación del servicio
        </label>
      </fieldset>

      <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
        <legend>Reducción de no-show (TASK-0036)</legend>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.no_show_confirmation_enabled}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, no_show_confirmation_enabled: e.target.checked })}
          />
          Enviar confirmación activa antes de la cita
        </label>
        <label>
          Horas antes de la cita
          <input
            type="number"
            min="1"
            max="48"
            value={notificationSettings.confirmation_reminder_hours}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, confirmation_reminder_hours: Number(e.target.value) || 0 })}
          />
        </label>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.auto_rebook_on_decline !== false}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, auto_rebook_on_decline: e.target.checked })}
          />
          Ofrecer reprogramar al declinar la confirmación (TASK-0044)
        </label>
        <p className="hint" style={{ marginTop: '0.25rem' }}>
          Si el cliente responde "no" al pedido de confirmación activa, el bot ofrecerá tres
          horarios alternativos en lugar de quedarse esperando a un agente. Si responde "no"
          al rebooking, la cita se cancela y se escala al equipo.
        </p>
        <label>
          Tiempo máximo del auto-rebook (min)
          <input
            type="number"
            min="10"
            max="240"
            value={notificationSettings.auto_rebook_timeout_minutes ?? 90}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, auto_rebook_timeout_minutes: Number(e.target.value) || 0 })}
          />
        </label>
        <p className="hint" style={{ marginTop: '0.25rem' }}>
          Si el cliente recibe los horarios y no responde dentro de esta ventana, la cita se
          cancela y la conversación se escala con la etiqueta "Necesita seguimiento"
          (TASK-0056). Rango 10–240 min, por defecto 90.
        </p>
        <label className="inline-check wide" data-wizard-field="ask_referrer">
          <input
            type="checkbox"
            checked={notificationSettings.ask_referrer === true}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, ask_referrer: e.target.checked })}
          />
          Preguntar "¿quién te recomendó?" al iniciar el booking (TASK-0055)
        </label>
        <p className="hint" style={{ marginTop: '0.25rem' }}>
          Captura al embajador para medir referidos en Analítica → Top
          referidores. Default desactivado.
        </p>
      </fieldset>

      <ComplaintAlertChannelsFieldset
        notificationSettings={notificationSettings}
        setNotificationSettings={setNotificationSettings}
      />

      {currentTenantId ? (
        <DigestSubscriptionsPanel session={session} tenantId={currentTenantId} />
      ) : (
        <p className="hint">
          Crea el tenant antes de configurar suscripciones al resumen periódico (TASK-0067).
        </p>
      )}

      <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
        <legend>Flujo post-cita (TASK-0036)</legend>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.post_instructions_enabled}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, post_instructions_enabled: e.target.checked })}
          />
          Enviar instrucciones post-servicio
        </label>
        <label>
          Minutos después del final
          <input
            type="number"
            min="0"
            max="1440"
            value={notificationSettings.post_instructions_delay_minutes}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, post_instructions_delay_minutes: Number(e.target.value) || 0 })}
          />
        </label>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.post_feedback_enabled}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, post_feedback_enabled: e.target.checked })}
          />
          Pedir feedback al cliente (1–5)
        </label>
        <label>
          Horas después del final
          <input
            type="number"
            min="0"
            max="168"
            value={notificationSettings.post_feedback_delay_hours}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, post_feedback_delay_hours: Number(e.target.value) || 0 })}
          />
        </label>
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={notificationSettings.post_rebooking_enabled}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, post_rebooking_enabled: e.target.checked })}
          />
          Invitar a nueva cita
        </label>
        <label>
          Días después
          <input
            type="number"
            min="1"
            max="365"
            value={notificationSettings.post_rebooking_delay_days}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, post_rebooking_delay_days: Number(e.target.value) || 0 })}
          />
        </label>
        <label className="wide">
          Mensaje personalizado de rebooking
          <textarea
            rows={2}
            value={notificationSettings.post_rebooking_message}
            onChange={(e) => setNotificationSettings({ ...notificationSettings, post_rebooking_message: e.target.value })}
            placeholder="Hola {{1}}, ya pasó un tiempo desde tu última visita. ¿Te gustaría agendar?"
          />
        </label>
      </fieldset>

      <div className="builder-preview wide">
        <strong>Preview del mensaje de confirmación</strong>
        <pre>{`Hola {nombre},

Tu cita de {servicio} quedó agendada para el {fecha} a las {hora}` + (notificationSettings.include_location_link && notificationSettings.location_address ? `\n\n📍 ${notificationSettings.location_address}` : '') + (notificationSettings.include_location_link && notificationSettings.location_maps_url ? `\n${notificationSettings.location_maps_url}` : '') + (notificationSettings.include_preparation_notes ? '\n\n📋 Instrucciones de preparación (del catálogo del servicio).' : '')}</pre>
      </div>

      <div className="form-actions">
        <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
          Guardar notificaciones
        </button>
      </div>
    </form>
  );
}
