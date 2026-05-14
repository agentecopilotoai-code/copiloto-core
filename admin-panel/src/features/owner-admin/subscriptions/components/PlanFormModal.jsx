import { FormField, Modal } from '../../../../components/ui/index.js';
import { BILLING_PERIODS } from '../subscriptionsData.js';
import styles from '../Subscriptions.module.css';

/**
 * Create / edit modal for a subscription plan. Reuses the `Modal` primitive;
 * presentational — all state and the mutation actions come from the
 * `useSubscriptionsData` hook via props.
 *
 * @param {{
 *   open: boolean,
 *   form: object,
 *   saving: boolean,
 *   onFieldChange: (patch: object) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function PlanFormModal({ open, form, saving, onFieldChange, onSubmit, onClose }) {
  if (!open) return null;

  const set = (key) => (event) => onFieldChange({ [key]: event.target.value });

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={form.id ? 'Editar plan' : 'Nuevo plan'}
      description="Plan de suscripción con cobro recurrente. El webhook de pagos reconcilia los eventos de Stripe y MercadoPago."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="subscription-plan-form"
            className={styles.primaryButton}
            disabled={saving}
          >
            {form.id ? 'Guardar cambios' : 'Crear plan'}
          </button>
        </div>
      }
    >
      <form
        id="subscription-plan-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField label="Nombre del plan" required>
          <input
            type="text"
            maxLength={200}
            required
            value={form.name}
            onChange={set('name')}
            placeholder="Ej. Membresía VIP mensual"
          />
        </FormField>
        <FormField label="Descripción">
          <input
            type="text"
            maxLength={2000}
            value={form.description}
            onChange={set('description')}
          />
        </FormField>
        <div className={styles.formRow}>
          <FormField label="Frecuencia">
            <select value={form.billing_period} onChange={set('billing_period')}>
              {BILLING_PERIODS.map((bp) => (
                <option key={bp.value} value={bp.value}>
                  {bp.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Precio">
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.price_amount}
              onChange={set('price_amount')}
            />
          </FormField>
          <FormField label="Moneda">
            <input
              type="text"
              maxLength={3}
              value={form.currency}
              onChange={set('currency')}
            />
          </FormField>
        </div>

        <label className={styles.check}>
          <input
            type="checkbox"
            checked={form.status === 'active'}
            onChange={(event) =>
              onFieldChange({ status: event.target.checked ? 'active' : 'archived' })
            }
          />
          Plan activo
        </label>
      </form>
    </Modal>
  );
}
