import { FormField, Modal } from '../../../../components/ui/index.js';
import styles from '../CampaignsModule.module.css';

/**
 * Create / edit drawer for a campaign. Reuses the `Modal` primitive;
 * presentational — all state and the submit action come from the
 * `useCampaignsData` hook via props. The form fields, the saved-segment
 * picker (`segment_id` via `listContactSegments`) and the alternative segment
 * filters are preserved verbatim from the legacy `CampaignsModule`.
 *
 * @param {{
 *   open: boolean,
 *   formMode: 'create' | 'edit',
 *   form: object,
 *   templates: Array<object>,
 *   segments: Array<object>,
 *   availableTags: Array<object>,
 *   isBusy: boolean,
 *   onChange: (form: object) => void,
 *   onToggleTag: (tagId: string) => void,
 *   onSubmit: () => void,
 *   onClose: () => void,
 * }} props
 */
export function CampaignFormDrawer({
  open,
  formMode,
  form,
  templates,
  segments,
  availableTags,
  isBusy,
  onChange,
  onToggleTag,
  onSubmit,
  onClose,
}) {
  if (!open) return null;

  const set = (key) => (event) => onChange({ ...form, [key]: event.target.value });
  const setSegment = (key) => (event) =>
    onChange({ ...form, segment: { ...form.segment, [key]: event.target.value } });

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={formMode === 'create' ? 'Nueva campaña' : 'Editar campaña'}
      description="Las campañas envían un template aprobado a contactos que cumplen los criterios definidos. Solo se entrega a contactos con opt-in válido."
      footer={
        <div className={styles.modalActions}>
          <button type="button" className={styles.secondaryButton} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="campaign-form"
            className={styles.primaryButton}
            disabled={isBusy || !form.name.trim() || !form.template_id}
          >
            {formMode === 'create' ? 'Crear borrador' : 'Guardar cambios'}
          </button>
        </div>
      }
    >
      <form
        id="campaign-form"
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
            placeholder="Promo octubre clientes inactivos"
          />
        </FormField>

        <FormField
          label="Template aprobado"
          required
          hint={
            templates.length === 0
              ? 'No hay templates aprobados. Crea uno en el módulo WhatsApp.'
              : undefined
          }
        >
          <select required value={form.template_id} onChange={set('template_id')}>
            <option value="">— Selecciona un template —</option>
            {templates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name} ({tpl.locale}) · {tpl.purpose}
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Variables (una por línea: clave=valor)">
          <textarea
            rows={4}
            value={form.template_variables}
            onChange={set('template_variables')}
            placeholder={'1=María\n2=20%'}
          />
        </FormField>

        <FormField label="Fecha/hora de envío (opcional)">
          <input
            type="datetime-local"
            value={form.scheduled_at}
            onChange={set('scheduled_at')}
          />
        </FormField>

        <FormField
          label="Segmento guardado"
          hint={
            form.segment_id
              ? 'Al lanzar la campaña, el segmento se snapshotea y los destinatarios quedan fijos.'
              : undefined
          }
        >
          <select value={form.segment_id} onChange={set('segment_id')}>
            <option value="">— Sin segmento (usar filtros) —</option>
            {segments.map((seg) => (
              <option key={seg.id} value={seg.id}>
                {seg.name} ({seg.contact_count})
              </option>
            ))}
          </select>
        </FormField>

        <fieldset
          className={styles.segmentFieldset}
          disabled={Boolean(form.segment_id)}
          data-disabled={form.segment_id ? 'true' : 'false'}
        >
          <legend>Filtros de segmento (alternativos)</legend>
          <div className={styles.formRow}>
            <FormField label="Mínimo de citas">
              <input
                type="number"
                min={0}
                value={form.segment.min_appointments}
                onChange={setSegment('min_appointments')}
              />
            </FormField>
            <FormField label="Última visita hace al menos (días)">
              <input
                type="number"
                min={0}
                value={form.segment.last_visit_before_days}
                onChange={setSegment('last_visit_before_days')}
              />
            </FormField>
            <FormField label="Última visita hace máximo (días)">
              <input
                type="number"
                min={0}
                value={form.segment.last_visit_after_days}
                onChange={setSegment('last_visit_after_days')}
              />
            </FormField>
            <FormField label="Cita futura agendada">
              <select
                value={form.segment.has_upcoming_appointment}
                onChange={setSegment('has_upcoming_appointment')}
              >
                <option value="">Sin filtro</option>
                <option value="yes">Sí, tiene cita futura</option>
                <option value="no">No tiene cita futura</option>
              </select>
            </FormField>
          </div>
          <div className={styles.tagSection}>
            <strong>Etiquetas</strong>
            <div className={styles.tagRow}>
              {availableTags.length === 0 ? (
                <small className={styles.hint}>No hay etiquetas configuradas.</small>
              ) : null}
              {availableTags.map((tag) => {
                const active = form.segment.tags.includes(tag.id);
                return (
                  <button
                    type="button"
                    key={tag.id}
                    onClick={() => onToggleTag(tag.id)}
                    className={active ? styles.tagPillActive : styles.tagPill}
                  >
                    {tag.name}
                  </button>
                );
              })}
            </div>
          </div>
        </fieldset>
      </form>
    </Modal>
  );
}
