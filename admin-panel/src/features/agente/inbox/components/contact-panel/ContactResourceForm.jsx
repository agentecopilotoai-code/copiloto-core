import { WORKING_DAYS } from '../../inboxData.js';
import styles from '../../OperationsDesk.module.css';

/**
 * ContactResourceForm — the resource builder form (code / name / type, the
 * public specialist profile fieldset and the weekly working-hours builder) plus
 * the tenant resource list. Presentational; create / edit / cancel handlers
 * live in `useContactPanelData`. Ported verbatim from the legacy module,
 * including the `specialist-profile-fields` / `working-hours-builder` markup.
 *
 * @param {object} props
 * @param {object} props.resourceForm
 * @param {string|null} props.editingResourceId
 * @param {Array<object>} props.imageAssets
 * @param {Array<object>} props.resources
 * @param {boolean} props.isBusy
 * @param {(form: object) => void} props.onResourceFormChange
 * @param {(event: Event) => void} props.onCreateResource
 * @param {(resource: object) => void} props.onEditResource
 * @param {() => void} props.onCancelResourceEdit
 */
export function ContactResourceForm({
  resourceForm,
  editingResourceId,
  imageAssets,
  resources,
  isBusy,
  onResourceFormChange,
  onCreateResource,
  onEditResource,
  onCancelResourceEdit,
}) {
  return (
    <>
      <form className="schedule-form" onSubmit={onCreateResource}>
        <label>
          Código recurso
          <input
            onChange={(event) =>
              onResourceFormChange({ ...resourceForm, code: event.target.value })}
            placeholder="TEC-01"
            value={resourceForm.code}
          />
        </label>
        <label>
          Nombre recurso
          <input
            onChange={(event) =>
              onResourceFormChange({ ...resourceForm, name: event.target.value })}
            placeholder="Técnico / silla / sala"
            value={resourceForm.name}
          />
        </label>
        <label>
          Tipo
          <select
            onChange={(event) =>
              onResourceFormChange({ ...resourceForm, resourceType: event.target.value })}
            value={resourceForm.resourceType}
          >
            <option value="technician">Técnico</option>
            <option value="chair">Silla</option>
            <option value="stylist">Estilista</option>
            <option value="groomer">Groomer</option>
            <option value="room">Sala</option>
            <option value="vehicle">Vehículo</option>
          </select>
        </label>
        <fieldset className="specialist-profile-fields">
          <legend>Perfil público del especialista</legend>
          <label>
            Especialidad
            <input
              onChange={(event) =>
                onResourceFormChange({ ...resourceForm, specialty: event.target.value })}
              placeholder="Ej: Odontología estética"
              value={resourceForm.specialty}
            />
          </label>
          <label>
            Bio breve (máx. 280 caracteres recomendado)
            <textarea
              maxLength={2000}
              onChange={(event) =>
                onResourceFormChange({ ...resourceForm, bio: event.target.value })}
              placeholder="Bio que el cliente verá en WhatsApp / widget"
              rows={3}
              value={resourceForm.bio}
            />
          </label>
          <label>
            Foto del especialista
            <select
              onChange={(event) =>
                onResourceFormChange({ ...resourceForm, photoMediaAssetId: event.target.value })}
              value={resourceForm.photoMediaAssetId}
            >
              <option value="">Sin foto</option>
              {imageAssets.map((asset) => (
                <option key={asset.id} value={asset.id}>{asset.label}</option>
              ))}
            </select>
          </label>
          <label>
            Licencia / registro profesional
            <input
              onChange={(event) =>
                onResourceFormChange({ ...resourceForm, licenseNumber: event.target.value })}
              placeholder="Opcional"
              value={resourceForm.licenseNumber}
            />
          </label>
          <label>
            Años de experiencia
            <input
              min="0"
              max="99"
              onChange={(event) =>
                onResourceFormChange({ ...resourceForm, yearsOfExperience: event.target.value })}
              placeholder="Opcional"
              type="number"
              value={resourceForm.yearsOfExperience}
            />
          </label>
          <label className="inline-check">
            <input
              checked={resourceForm.publicProfile}
              onChange={(event) =>
                onResourceFormChange({ ...resourceForm, publicProfile: event.target.checked })}
              type="checkbox"
            />
            Mostrar este recurso públicamente al cliente (booking y widget)
          </label>
        </fieldset>
        <fieldset className="working-hours-builder">
          <legend>Horario laboral semanal</legend>
          {WORKING_DAYS.map(({ key, label }) => {
            const day = resourceForm.workingHours[key];
            return (
              <div className="working-hours-row" key={key}>
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={day.enabled}
                    onChange={(event) =>
                      onResourceFormChange({
                        ...resourceForm,
                        workingHours: {
                          ...resourceForm.workingHours,
                          [key]: { ...day, enabled: event.target.checked },
                        },
                      })}
                  />
                  {label}
                </label>
                <input
                  type="time"
                  value={day.start}
                  disabled={!day.enabled}
                  onChange={(event) =>
                    onResourceFormChange({
                      ...resourceForm,
                      workingHours: {
                        ...resourceForm.workingHours,
                        [key]: { ...day, start: event.target.value },
                      },
                    })}
                />
                <span> – </span>
                <input
                  type="time"
                  value={day.end}
                  disabled={!day.enabled}
                  onChange={(event) =>
                    onResourceFormChange({
                      ...resourceForm,
                      workingHours: {
                        ...resourceForm.workingHours,
                        [key]: { ...day, end: event.target.value },
                      },
                    })}
                />
              </div>
            );
          })}
        </fieldset>
        <div className="form-actions">
          <button className="secondary-action" disabled={isBusy} type="submit">
            {editingResourceId ? 'Guardar cambios' : 'Crear recurso'}
          </button>
          {editingResourceId ? (
            <button
              className={`secondary-action ${styles.cancelEditButton}`}
              disabled={isBusy}
              onClick={onCancelResourceEdit}
              type="button"
            >
              Cancelar edición
            </button>
          ) : null}
        </div>
      </form>

      {resources.length ? (
        <div className="resource-list">
          <strong>Recursos del tenant</strong>
          <ul>
            {resources.map((resource) => (
              <li key={resource.id}>
                <span>{resource.name} · <code>{resource.code}</code></span>
                <button
                  className="secondary-action"
                  type="button"
                  onClick={() => onEditResource(resource)}
                >
                  Editar horario
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}
