import { FormField, Modal } from '../../../../components/ui/index.js';
import { MEDIA_KIND_LABELS, PROMO_MEDIA_KINDS } from '../mediaLibraryData.js';
import styles from '../MediaLibraryModule.module.css';

/**
 * Create / edit drawer for a promotion. Reuses the `Modal` primitive;
 * presentational — all state and the submit action come from the
 * `useMediaLibraryData` hook via props.
 *
 * @param {{
 *   open: boolean,
 *   promoForm: object,
 *   editingPromoId: string | null,
 *   assets: Array<object>,
 *   services: Array<object>,
 *   isBusy: boolean,
 *   onChange: (form: object) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function PromotionFormDrawer({
  open,
  promoForm,
  editingPromoId,
  assets,
  services,
  isBusy,
  onChange,
  onSubmit,
  onClose,
}) {
  if (!open) return null;

  const set = (key) => (event) => onChange({ ...promoForm, [key]: event.target.value });
  const promoAssets = assets.filter((asset) => PROMO_MEDIA_KINDS.includes(asset.kind));

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={editingPromoId ? 'Editar promoción' : 'Nueva promoción'}
      description="Las promociones se vinculan a servicios — el bot las ofrece automáticamente cuando aplican."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="promo-form"
            className={styles.primaryButton}
            disabled={isBusy || !promoForm.name.trim()}
          >
            {editingPromoId ? 'Guardar cambios' : 'Crear promoción'}
          </button>
        </div>
      }
    >
      <form
        id="promo-form"
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField label="Nombre" required>
          <input
            type="text"
            required
            maxLength={200}
            value={promoForm.name}
            onChange={set('name')}
            placeholder="Ej. Limpieza dental 20% - mayo"
          />
        </FormField>
        <FormField label="Descripción / texto que envía el bot">
          <textarea
            rows={3}
            maxLength={2000}
            value={promoForm.description}
            onChange={set('description')}
          />
        </FormField>
        <FormField label="Imagen / video asociado">
          <select value={promoForm.media_asset_id || ''} onChange={set('media_asset_id')}>
            <option value="">— Sin medio (solo texto) —</option>
            {promoAssets.map((asset) => (
              <option key={asset.id} value={asset.id}>
                {MEDIA_KIND_LABELS[asset.kind]}: {asset.label}
              </option>
            ))}
          </select>
        </FormField>
        <FormField
          label="Aplica a servicios"
          hint="Vacío = aplica a todos los servicios del tenant."
        >
          <select
            multiple
            className={styles.multiSelect}
            value={promoForm.applies_to_service_ids}
            onChange={(event) =>
              onChange({
                ...promoForm,
                applies_to_service_ids: Array.from(event.target.selectedOptions).map(
                  (option) => option.value,
                ),
              })
            }
          >
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
          </select>
        </FormField>
        <div className={styles.formRow}>
          <FormField label="Vigencia desde">
            <input
              type="datetime-local"
              value={promoForm.valid_from}
              onChange={set('valid_from')}
            />
          </FormField>
          <FormField label="Vigencia hasta">
            <input
              type="datetime-local"
              value={promoForm.valid_until}
              onChange={set('valid_until')}
            />
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Código de cupón">
            <input
              type="text"
              maxLength={80}
              value={promoForm.coupon_code}
              onChange={set('coupon_code')}
            />
          </FormField>
          <FormField label="Descuento (%)">
            <input
              type="number"
              min="0"
              max="100"
              step="0.5"
              value={promoForm.discount_percent}
              onChange={set('discount_percent')}
            />
          </FormField>
        </div>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={promoForm.is_active}
            onChange={(event) => onChange({ ...promoForm, is_active: event.target.checked })}
          />
          Promoción activa
        </label>
      </form>
    </Modal>
  );
}
