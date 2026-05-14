import { weekdays } from '../tenantSetupData.js';

export function ScheduleTab({ state, actions }) {
  const { hoursForm, isBusy, currentTenantId } = state;
  const { handleSaveSettings, setHoursForm } = actions;

  return (
    <form className="wizard-panel" onSubmit={handleSaveSettings}>
      <div className="hours-grid">
        {weekdays.map(([day, label]) => (
          <fieldset className="day-card" key={day}>
            <legend>{label}</legend>
            <label className="inline-check">
              <input checked={hoursForm[day].enabled} onChange={(event) => setHoursForm({ ...hoursForm, [day]: { ...hoursForm[day], enabled: event.target.checked } })} type="checkbox" />
              Activo
            </label>
            <label>
              Inicio
              <input value={hoursForm[day].start} onChange={(event) => setHoursForm({ ...hoursForm, [day]: { ...hoursForm[day], start: event.target.value } })} type="time" />
            </label>
            <label>
              Fin
              <input value={hoursForm[day].end} onChange={(event) => setHoursForm({ ...hoursForm, [day]: { ...hoursForm[day], end: event.target.value } })} type="time" />
            </label>
          </fieldset>
        ))}
      </div>
      <div className="form-actions">
        <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar horarios</button>
      </div>
    </form>
  );
}
