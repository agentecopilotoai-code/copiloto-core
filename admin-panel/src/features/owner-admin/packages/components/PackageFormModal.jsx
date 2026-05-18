import { AlertBanner, FormField, Modal } from '../../../../components/ui/index.js';
import styles from '../Packages.module.css';

/**
 * Create / edit modal for a treatment package. Reuses the `Modal` primitive;
 * presentational — all state and the mutation actions come from the
 * `usePackagesData` hook via props.
 *
 * BUG-113: surface `error` inline en el body del modal. Antes el AlertBanner
 * del outer `<Packages>` quedaba detrás del backdrop cuando el modal estaba
 * abierto, así que un save-fail no daba ningún feedback visible al usuario.
 *
 * @param {{
 *   open: boolean,
 *   form: object,
 *   services: Array<object>,
 *   saving: boolean,
 *   error?: string,
 *   onFieldChange: (patch: object) => void,
 *   onToggleService: (serviceId: string) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 *   onDismissError?: () => void,
 * }} props
 */
export function PackageFormModal({
  open,
  form,
  services,
  saving,
  error,
  onFieldChange,
  onToggleService,
  onSubmit,
  onClose,
  onDismissError,
}) {
  if (!open) return null;

  const set = (key) => (event) => onFieldChange({ [key]: event.target.value });

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={form.id ? 'Editar paquete' : 'Nuevo paquete'}
      description="Plan multi-cita con saldo de sesiones. El saldo decrementa al completar una cita asociada."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="package-form"
            className={styles.primaryButton}
            disabled={saving}
          >
            {form.id ? 'Guardar cambios' : 'Crear paquete'}
          </button>
        </div>
      }
    >
      <form
        id="package-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        {/* BUG-113: error inline en el body del modal — fuera del modal el
            AlertBanner quedaba detrás del backdrop y el save-fail no daba
            ningún feedback visible al usuario. */}
        {error ? (
          <AlertBanner
            tone="danger"
            title={error}
            action={
              onDismissError ? (
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={onDismissError}
                >
                  Cerrar
                </button>
              ) : null
            }
          />
        ) : null}
        <FormField label="Nombre" required>
          <input
            type="text"
            maxLength={200}
            required
            value={form.name}
            onChange={set('name')}
            placeholder="Ej. 5 sesiones de fisioterapia"
          />
        </FormField>
        <FormField label="Descripción">
          <input type="text" maxLength={2000} value={form.description} onChange={set('description')} />
        </FormField>
        <div className={styles.formRow}>
          <FormField label="Total de sesiones" required>
            <input
              type="number"
              min="1"
              max="500"
              required
              value={form.total_sessions}
              onChange={set('total_sessions')}
            />
          </FormField>
          <FormField label="Vencimiento (días)">
            <input
              type="number"
              min="1"
              max="3650"
              value={form.validity_days}
              onChange={set('validity_days')}
              placeholder="Sin vencimiento"
            />
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Precio">
            <input type="number" min="0" step="0.01" value={form.price_amount} onChange={set('price_amount')} />
          </FormField>
          <FormField label="Moneda">
            <input type="text" maxLength={3} value={form.price_currency} onChange={set('price_currency')} />
          </FormField>
          <FormField label="Orden">
            <input type="number" min="0" value={form.sort_order} onChange={set('sort_order')} />
          </FormField>
        </div>

        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>Servicios incluidos (vacío = todos)</legend>
          {services.length === 0 ? (
            <p className={styles.hint}>No hay servicios activos.</p>
          ) : (
            <ul className={styles.serviceList}>
              {services.map((svc) => (
                <li key={svc.id}>
                  <label className={styles.check}>
                    <input
                      type="checkbox"
                      checked={form.includes_service_ids.includes(svc.id)}
                      onChange={() => onToggleService(svc.id)}
                    />
                    {svc.name}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>

        <label className={styles.check}>
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(event) => onFieldChange({ is_active: event.target.checked })}
          />
          Activo
        </label>
      </form>
    </Modal>
  );
}
