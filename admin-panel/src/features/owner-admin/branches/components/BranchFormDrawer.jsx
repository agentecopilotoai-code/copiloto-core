import { FormField, Modal } from '../../../../components/ui/index.js';
import { TIMEZONE_OPTIONS } from '../branchesData.js';
import { OpeningHoursEditor } from './OpeningHoursEditor.jsx';
import styles from '../Branches.module.css';

/**
 * Create / edit drawer for a branch. Reuses the `Modal` primitive; composes
 * `OpeningHoursEditor` for the per-day schedule. Presentational — all state and
 * the mutation actions come from the `useBranchesData` hook via props. The
 * Maps-URL generator mirrors the backend (`buildMapsUrlFromInputs`,
 * TASK-0058).
 *
 * @param {{
 *   open: boolean,
 *   form: object,
 *   saving: boolean,
 *   mapsPreviewUrl: string | null,
 *   onFieldChange: (patch: object) => void,
 *   onGenerateMapsUrl: () => void,
 *   onAddFranja: (dayKey: string) => void,
 *   onRemoveFranja: (dayKey: string, index: number) => void,
 *   onUpdateFranja: (dayKey: string, index: number, field: string, value: string) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function BranchFormDrawer({
  open,
  form,
  saving,
  mapsPreviewUrl,
  onFieldChange,
  onGenerateMapsUrl,
  onAddFranja,
  onRemoveFranja,
  onUpdateFranja,
  onSubmit,
  onClose,
}) {
  if (!open) return null;

  const set = (key) => (event) => onFieldChange({ [key]: event.target.value });

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={form.id ? 'Editar sede' : 'Nueva sede'}
      description="Cada sede tiene su propia dirección, horario y teléfono. Los recordatorios envían la dirección y el mapa de la sede de la cita."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="branch-form"
            className={styles.primaryButton}
            disabled={saving}
          >
            {form.id ? 'Guardar cambios' : 'Crear sede'}
          </button>
        </div>
      }
    >
      <form
        id="branch-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className={styles.formRow}>
          <FormField label="Nombre" required>
            <input
              type="text"
              maxLength={160}
              required
              value={form.name}
              onChange={set('name')}
              placeholder="Ej. Sede Chapinero"
            />
          </FormField>
          <FormField label="Código (único por tenant)" required>
            <input
              type="text"
              maxLength={80}
              required
              value={form.code}
              onChange={set('code')}
              placeholder="chapinero"
            />
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Dirección">
            <input type="text" maxLength={500} value={form.address} onChange={set('address')} />
          </FormField>
          <FormField label="Ciudad">
            <input type="text" maxLength={120} value={form.city} onChange={set('city')} />
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Departamento / Estado">
            <input type="text" maxLength={120} value={form.state} onChange={set('state')} />
          </FormField>
          <FormField label="País (ISO-2)">
            <input type="text" maxLength={2} value={form.country} onChange={set('country')} />
          </FormField>
          <FormField label="Teléfono (E.164)">
            <input
              type="text"
              maxLength={32}
              value={form.phone_e164}
              onChange={set('phone_e164')}
              placeholder="+57..."
            />
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Latitud">
            <input
              type="number"
              step="0.0000001"
              value={form.lat}
              onChange={set('lat')}
            />
          </FormField>
          <FormField label="Longitud">
            <input
              type="number"
              step="0.0000001"
              value={form.lng}
              onChange={set('lng')}
            />
          </FormField>
          <FormField label="Zona horaria">
            <select value={form.timezone} onChange={set('timezone')}>
              {TIMEZONE_OPTIONS.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </FormField>
        </div>

        <FormField
          label="Maps URL"
          hint="Se autogenera al guardar si lo dejas vacío. Prioriza lat/lng sobre la dirección."
        >
          <input
            type="text"
            maxLength={500}
            value={form.maps_url}
            onChange={set('maps_url')}
            placeholder="https://maps.google.com/..."
            data-testid="branches-maps-url"
          />
        </FormField>
        <div className={styles.mapsActions}>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={onGenerateMapsUrl}
            disabled={!mapsPreviewUrl}
            data-testid="branches-maps-generate"
          >
            Generar desde la dirección
          </button>
          {form.maps_url ? (
            <a
              href={form.maps_url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.mapsLink}
            >
              Abrir enlace actual
            </a>
          ) : null}
        </div>
        {mapsPreviewUrl ? (
          <p className={`${styles.hint} branches-maps-preview`}>
            Vista previa:{' '}
            <a href={mapsPreviewUrl} target="_blank" rel="noopener noreferrer">
              abrir en Google Maps
            </a>
          </p>
        ) : null}

        <OpeningHoursEditor
          openingHours={form.opening_hours}
          onAddFranja={onAddFranja}
          onRemoveFranja={onRemoveFranja}
          onUpdateFranja={onUpdateFranja}
        />

        <div className={styles.formRow}>
          <FormField label="Orden">
            <input type="number" min="0" value={form.sort_order} onChange={set('sort_order')} />
          </FormField>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => onFieldChange({ is_active: event.target.checked })}
            />
            Sede activa
          </label>
        </div>
      </form>
    </Modal>
  );
}
