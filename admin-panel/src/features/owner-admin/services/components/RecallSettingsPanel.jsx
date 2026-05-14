import { FormField } from '../../../../components/ui/index.js';
import { formatRecallPreview } from '../servicesData.js';
import styles from '../Services.module.css';

/**
 * Recall configuration block of the service form (TASK-0052): the per-service
 * recall interval and the approved `service_recall` template to send. An empty
 * interval means "no recall"; the panel shows the date a recall would land if
 * a matching appointment completed today.
 *
 * @param {{
 *   form: object,
 *   recallTemplates: Array<object>,
 *   onChange: (patch: object) => void,
 * }} props
 */
export function RecallSettingsPanel({ form, recallTemplates, onChange }) {
  const preview = formatRecallPreview(form.recall_interval_days);
  const intervalSet = Boolean(form.recall_interval_days);

  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>Recordatorio de control</legend>
      <FormField
        label="Recordatorio de control cada N días"
        hint={
          preview
            ? `Si lo dejas vacío no se envía recordatorio. Una cita completada hoy dispararía el recordatorio el ${preview}.`
            : 'Si lo dejas vacío no se envía recordatorio.'
        }
      >
        <input
          type="number"
          min="0"
          max="3650"
          step="1"
          placeholder="Ej. 180 para control semestral"
          value={form.recall_interval_days}
          onChange={(event) => onChange({ recall_interval_days: event.target.value })}
        />
      </FormField>
      <FormField
        label="Plantilla del recordatorio"
        error={
          intervalSet && recallTemplates.length === 0
            ? 'No hay plantillas service_recall aprobadas. Crea una en WhatsApp Templates antes de programar recordatorios.'
            : undefined
        }
      >
        <select
          value={form.recall_template_id || ''}
          disabled={!form.recall_interval_days}
          onChange={(event) => onChange({ recall_template_id: event.target.value })}
        >
          <option value="">— Usar la plantilla aprobada por defecto —</option>
          {recallTemplates.map((tmpl) => (
            <option key={tmpl.id} value={tmpl.id}>
              {tmpl.name} ({tmpl.locale})
            </option>
          ))}
        </select>
      </FormField>
    </fieldset>
  );
}
