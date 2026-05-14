import { Card, CardHeader, FormField } from '../../../../components/ui/index.js';
import { CURRENCIES } from '../servicesData.js';
import { RecallSettingsPanel } from './RecallSettingsPanel.jsx';
import { AppliesWhenBuilder } from './AppliesWhenBuilder.jsx';
import styles from '../Services.module.css';

/**
 * Create / edit form for a service. Composes `RecallSettingsPanel` (TASK-0052)
 * and `AppliesWhenBuilder` (TASK-0054); presentational — all state and the
 * mutation actions come from the `useServicesData` hook via props.
 *
 * @param {{
 *   form: object,
 *   editingId: string|null,
 *   isBusy: boolean,
 *   recallTemplates: Array<object>,
 *   qualificationKeys: Array<object>,
 *   previewText: string,
 *   onFieldChange: (patch: object) => void,
 *   onSubmit: () => void,
 *   onCancel: () => void,
 *   onAddRule: () => void,
 *   onUpdateRule: (index: number, patch: object) => void,
 *   onRemoveRule: (index: number) => void,
 * }} props
 */
export function ServiceFormDrawer({
  form,
  editingId,
  isBusy,
  recallTemplates,
  qualificationKeys,
  previewText,
  onFieldChange,
  onSubmit,
  onCancel,
  onAddRule,
  onUpdateRule,
  onRemoveRule,
}) {
  const set = (key) => (event) => onFieldChange({ [key]: event.target.value });

  return (
    <Card padding="md">
      <CardHeader title={editingId ? 'Editar servicio' : 'Nuevo servicio'} />
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <FormField label="Nombre" required>
          <input type="text" maxLength={160} required value={form.name} onChange={set('name')} />
        </FormField>
        <div className={styles.formRow}>
          <FormField label="Categoría">
            <input
              type="text"
              maxLength={120}
              placeholder="Ej. Corte, Manicure, Consulta"
              value={form.category}
              onChange={set('category')}
            />
          </FormField>
          <FormField label="Estado">
            <select
              value={form.is_active ? 'active' : 'inactive'}
              onChange={(event) => onFieldChange({ is_active: event.target.value === 'active' })}
            >
              <option value="active">Activo</option>
              <option value="inactive">Inactivo</option>
            </select>
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Precio">
            <input type="number" min="0" step="0.01" value={form.price_amount} onChange={set('price_amount')} />
          </FormField>
          <FormField label="Moneda">
            <select value={form.price_currency} onChange={set('price_currency')}>
              {CURRENCIES.map((currency) => (
                <option key={currency} value={currency}>
                  {currency}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Duración (minutos)" required>
            <input
              type="number"
              min="1"
              max="1440"
              required
              value={form.duration_minutes}
              onChange={set('duration_minutes')}
            />
          </FormField>
        </div>
        <FormField label="Descripción">
          <textarea maxLength={2000} rows={2} value={form.description} onChange={set('description')} />
        </FormField>
        <FormField label="Instrucciones de preparación (se envían antes del servicio)">
          <textarea
            maxLength={2000}
            rows={2}
            value={form.preparation_notes}
            onChange={set('preparation_notes')}
          />
        </FormField>
        <FormField label="Instrucciones post-servicio (se envían después)">
          <textarea
            maxLength={2000}
            rows={2}
            value={form.post_service_notes}
            onChange={set('post_service_notes')}
          />
        </FormField>

        <RecallSettingsPanel
          form={form}
          recallTemplates={recallTemplates}
          onChange={onFieldChange}
        />

        <AppliesWhenBuilder
          rules={form.applies_when_rules}
          qualificationKeys={qualificationKeys}
          onAdd={onAddRule}
          onUpdate={onUpdateRule}
          onRemove={onRemoveRule}
        />

        <div className={styles.preview}>
          <strong>Vista previa para WhatsApp</strong>
          <pre className={styles.previewBody}>{previewText}</pre>
        </div>

        <div className={styles.formActions}>
          <button type="submit" className={styles.primaryButton} disabled={isBusy}>
            {editingId ? 'Actualizar servicio' : 'Crear servicio'}
          </button>
          {editingId ? (
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={isBusy}
              onClick={onCancel}
            >
              Cancelar edición
            </button>
          ) : null}
        </div>
      </form>
    </Card>
  );
}
