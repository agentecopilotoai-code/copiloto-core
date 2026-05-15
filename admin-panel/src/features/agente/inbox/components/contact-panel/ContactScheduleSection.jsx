import { formatDate, PAYMENT_LABELS } from '../../inboxData.js';
import { ContactResourceForm } from './ContactResourceForm.jsx';

/**
 * ContactScheduleSection — the "Recursos y agenda" panel: the resource builder
 * (via `ContactResourceForm`), the daily availability calendar, the create /
 * reschedule appointment forms and the appointment list with the payment-link
 * block + feedback rating. Presentational; every mutation handler lives in
 * `useContactPanelData`. Ported verbatim from the legacy `OperationsDesk`.
 *
 * @param {object} props — the contact-panel state slice + handlers (see below)
 */
export function ContactScheduleSection({
  resourceForm,
  editingResourceId,
  imageAssets,
  resources,
  appointments,
  appointmentFeedback,
  calendarDate,
  calendarData,
  isCalendarLoading,
  appointmentForm,
  rescheduleForm,
  paymentDrafts,
  hasContact,
  isBusy,
  onResourceFormChange,
  onCreateResource,
  onEditResource,
  onCancelResourceEdit,
  onCalendarDateChange,
  onLoadCalendar,
  onAppointmentFormChange,
  onCreateAppointment,
  onRescheduleFormChange,
  onRescheduleAppointment,
  onPaymentDraftsChange,
  onGeneratePaymentLink,
  onSendPaymentLink,
  onMarkPaymentStatus,
  onCancelAppointment,
}) {
  return (
    <div className="schedule-panel">
      <div>
        <strong>Recursos y agenda</strong>
        <p className="hint">
          Configura recursos, agenda citas para el contacto seleccionado y reprograma/cancela sin
          solapar reservas activas.
        </p>
      </div>

      <ContactResourceForm
        resourceForm={resourceForm}
        editingResourceId={editingResourceId}
        imageAssets={imageAssets}
        resources={resources}
        isBusy={isBusy}
        onResourceFormChange={onResourceFormChange}
        onCreateResource={onCreateResource}
        onEditResource={onEditResource}
        onCancelResourceEdit={onCancelResourceEdit}
      />

      <div className="weekly-calendar">
        <div className="calendar-header">
          <strong>Calendario diario</strong>
          <input
            aria-label="Fecha del calendario diario"
            type="date"
            value={calendarDate}
            onChange={(event) => onCalendarDateChange(event.target.value)}
          />
          <button
            className="secondary-action"
            disabled={isCalendarLoading}
            onClick={() => onLoadCalendar()}
            type="button"
          >
            {isCalendarLoading ? 'Cargando…' : 'Refrescar'}
          </button>
        </div>
        {calendarData ? (
          <div className="calendar-grid">
            {(calendarData.resources || []).map((resource) => (
              <div className="calendar-resource" key={resource.resource_id}>
                <p className="calendar-resource-title">{resource.resource_name}</p>
                {resource.slots && resource.slots.length ? (
                  <div className="calendar-slots">
                    {resource.slots.slice(0, 12).map((slot) => (
                      <span
                        className="calendar-slot calendar-slot-free"
                        key={`${slot.start_time}-${slot.end_time}`}
                      >
                        {slot.start_time}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="hint">Sin cupos libres este día.</p>
                )}
              </div>
            ))}
            {(!calendarData.resources || calendarData.resources.length === 0) ? (
              <p className="hint">Sin recursos activos configurados.</p>
            ) : null}
          </div>
        ) : (
          <p className="hint">Selecciona una fecha para ver disponibilidad.</p>
        )}
      </div>

      <form className="schedule-form" onSubmit={onCreateAppointment}>
        <label>
          Recurso
          <select
            onChange={(event) =>
              onAppointmentFormChange({ ...appointmentForm, resourceId: event.target.value })}
            value={appointmentForm.resourceId}
          >
            <option value="">Selecciona recurso</option>
            {resources.filter((resource) => resource.is_active).map((resource) => (
              <option key={resource.id} value={resource.id}>
                {resource.name} ({resource.code})
              </option>
            ))}
          </select>
        </label>
        <label>
          Servicio
          <input
            onChange={(event) =>
              onAppointmentFormChange({ ...appointmentForm, serviceCode: event.target.value })}
            placeholder="diagnostico / corte / baño"
            value={appointmentForm.serviceCode}
          />
        </label>
        <label>
          Inicio
          <input
            onChange={(event) =>
              onAppointmentFormChange({ ...appointmentForm, startsAt: event.target.value })}
            type="datetime-local"
            value={appointmentForm.startsAt}
          />
        </label>
        <label>
          Fin
          <input
            onChange={(event) =>
              onAppointmentFormChange({ ...appointmentForm, endsAt: event.target.value })}
            type="datetime-local"
            value={appointmentForm.endsAt}
          />
        </label>
        <label>
          Notas
          <input
            onChange={(event) =>
              onAppointmentFormChange({ ...appointmentForm, notes: event.target.value })}
            placeholder="Notas internas"
            value={appointmentForm.notes}
          />
        </label>
        <button className="primary-action" disabled={isBusy || !hasContact} type="submit">
          Crear cita
        </button>
      </form>

      <form className="schedule-form" onSubmit={onRescheduleAppointment}>
        <label>
          Cita
          <select
            onChange={(event) =>
              onRescheduleFormChange({ ...rescheduleForm, appointmentId: event.target.value })}
            value={rescheduleForm.appointmentId}
          >
            <option value="">Selecciona cita activa</option>
            {appointments
              .filter((appointment) => ['scheduled', 'confirmed'].includes(appointment.status))
              .map((appointment) => (
                <option key={appointment.id} value={appointment.id}>
                  {formatDate(appointment.starts_at)} · {appointment.resource_name}
                </option>
              ))}
          </select>
        </label>
        <label>
          Nuevo recurso
          <select
            onChange={(event) =>
              onRescheduleFormChange({ ...rescheduleForm, resourceId: event.target.value })}
            value={rescheduleForm.resourceId}
          >
            <option value="">Selecciona recurso</option>
            {resources.filter((resource) => resource.is_active).map((resource) => (
              <option key={resource.id} value={resource.id}>
                {resource.name} ({resource.code})
              </option>
            ))}
          </select>
        </label>
        <label>
          Nuevo inicio
          <input
            onChange={(event) =>
              onRescheduleFormChange({ ...rescheduleForm, startsAt: event.target.value })}
            type="datetime-local"
            value={rescheduleForm.startsAt}
          />
        </label>
        <label>
          Nuevo fin
          <input
            onChange={(event) =>
              onRescheduleFormChange({ ...rescheduleForm, endsAt: event.target.value })}
            type="datetime-local"
            value={rescheduleForm.endsAt}
          />
        </label>
        <button className="secondary-action" disabled={isBusy} type="submit">Reprogramar</button>
      </form>

      <div className="appointment-list">
        {appointments.slice(0, 8).map((appointment) => {
          const confirmation = appointment.confirmation_status || 'pending';
          const feedback = appointmentFeedback[appointment.id];
          const paymentStatus = appointment.payment_status || 'not_required';
          const draft = paymentDrafts[appointment.id] || {};
          const amountValue = draft.amount !== undefined
            ? draft.amount
            : appointment.payment_amount ?? '';
          const currencyValue = draft.currency !== undefined
            ? draft.currency
            : appointment.payment_currency || 'COP';
          return (
            <article key={appointment.id}>
              <strong>
                {formatDate(appointment.starts_at)} — {formatDate(appointment.ends_at)}
              </strong>
              <small>
                {appointment.resource_name} · {appointment.service_code} · {appointment.status}
              </small>
              <div className="appointment-badges">
                <span className={`status-badge confirmation-${confirmation}`}>
                  {confirmation === 'confirmed'
                    ? 'Confirmada'
                    : confirmation === 'declined' ? 'Rechazada' : 'Pendiente'}
                </span>
                <span className={`status-badge payment-${paymentStatus}`}>
                  Pago: {PAYMENT_LABELS[paymentStatus] || paymentStatus}
                </span>
                {feedback ? (
                  <span className="status-badge feedback-rating" title={feedback.comment || ''}>
                    {'⭐'.repeat(feedback.rating)} ({feedback.rating}/5)
                  </span>
                ) : null}
              </div>

              <div className="appointment-payment">
                <label>
                  Monto
                  <input
                    min="0"
                    onChange={(event) =>
                      onPaymentDraftsChange({
                        ...paymentDrafts,
                        [appointment.id]: { ...draft, amount: event.target.value },
                      })}
                    placeholder="0"
                    step="0.01"
                    type="number"
                    value={amountValue ?? ''}
                  />
                </label>
                <label>
                  Moneda
                  <input
                    maxLength={3}
                    onChange={(event) =>
                      onPaymentDraftsChange({
                        ...paymentDrafts,
                        [appointment.id]: {
                          ...draft,
                          currency: event.target.value.toUpperCase(),
                        },
                      })}
                    value={currencyValue}
                  />
                </label>
                <div className="payment-actions">
                  <button
                    className="secondary-action"
                    disabled={isBusy}
                    onClick={() => onGeneratePaymentLink(appointment)}
                    type="button"
                  >
                    Generar link
                  </button>
                  <button
                    className="secondary-action"
                    disabled={isBusy || !appointment.payment_link}
                    onClick={() => onSendPaymentLink(appointment.id)}
                    type="button"
                  >
                    Enviar por WhatsApp
                  </button>
                  <button
                    className="secondary-action"
                    disabled={isBusy || paymentStatus === 'paid'}
                    onClick={() => onMarkPaymentStatus(appointment.id, 'paid')}
                    type="button"
                  >
                    Marcar pagado
                  </button>
                </div>
                {appointment.payment_link ? (
                  <small>
                    Link:&nbsp;
                    <a href={appointment.payment_link} rel="noreferrer" target="_blank">
                      {appointment.payment_link}
                    </a>
                  </small>
                ) : null}
              </div>

              {appointment.status !== 'cancelled' && (
                <button
                  className="secondary-action"
                  disabled={isBusy}
                  onClick={() => onCancelAppointment(appointment.id)}
                  type="button"
                >
                  Cancelar
                </button>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
