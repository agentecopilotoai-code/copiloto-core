import { FormField, Modal } from '../../../../components/ui/index.js';
import { KIND_LABELS } from '../segmentsData.js';
import { SegmentRuleBuilder } from './SegmentRuleBuilder.jsx';
import styles from '../SegmentsModule.module.css';

/**
 * Create / edit drawer for a segment. Reuses the `Modal` primitive;
 * presentational — all state and the submit action come from the
 * `useSegmentsData` hook via props. Composes `SegmentRuleBuilder` for the
 * dynamic rule array (only shown for `kind === 'dynamic'`). The form fields and
 * the kind selector are preserved verbatim from the legacy `SegmentsModule`.
 *
 * @param {{
 *   open: boolean,
 *   formMode: 'create' | 'edit',
 *   form: object,
 *   isBusy: boolean,
 *   onChange: (form: object) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 *   ruleActions: {
 *     onJoinerChange: (joiner: string) => void,
 *     onAddRule: () => void,
 *     onRemoveRule: (index: number) => void,
 *     onFieldChange: (index: number, field: string) => void,
 *     onOpChange: (index: number, op: string) => void,
 *     onValueChange: (index: number, rawValue: string) => void,
 *     onListValueBlur: (index: number, rawValue: string) => void,
 *   },
 * }} props
 */
export function SegmentFormDrawer({
  open,
  formMode,
  form,
  isBusy,
  onChange,
  onSubmit,
  onClose,
  ruleActions,
}) {
  if (!open) return null;

  const set = (key) => (event) => onChange({ ...form, [key]: event.target.value });

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={formMode === 'create' ? 'Nuevo segmento' : 'Editar segmento'}
      description="Los segmentos permiten reutilizar reglas (ej. «Sin visita en 60+ días») como destinatarios de campañas y filtros de contactos. Los segmentos dinámicos se recalculan automáticamente."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="segment-form"
            className={styles.primaryButton}
            disabled={isBusy || !form.name.trim()}
          >
            {formMode === 'create' ? 'Crear segmento' : 'Guardar cambios'}
          </button>
        </div>
      }
    >
      <form
        id="segment-form"
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
            value={form.name}
            onChange={set('name')}
            placeholder="Reactivación 60+ días"
          />
        </FormField>

        <FormField label="Descripción">
          <input
            type="text"
            value={form.description}
            onChange={set('description')}
            placeholder="Opcional"
          />
        </FormField>

        <FormField label="Tipo">
          <select value={form.kind} onChange={set('kind')}>
            <option value="dynamic">{KIND_LABELS.dynamic}</option>
            <option value="static">{KIND_LABELS.static}</option>
          </select>
        </FormField>

        {form.kind === 'dynamic' ? (
          <SegmentRuleBuilder
            joiner={form.joiner}
            items={form.items}
            onJoinerChange={ruleActions.onJoinerChange}
            onAddRule={ruleActions.onAddRule}
            onRemoveRule={ruleActions.onRemoveRule}
            onFieldChange={ruleActions.onFieldChange}
            onOpChange={ruleActions.onOpChange}
            onValueChange={ruleActions.onValueChange}
            onListValueBlur={ruleActions.onListValueBlur}
          />
        ) : null}
      </form>
    </Modal>
  );
}
