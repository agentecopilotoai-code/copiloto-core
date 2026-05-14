import {
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  FormField,
  StatusBadge,
} from '../../../../components/ui/index.js';
import {
  TEMPLATE_PURPOSES,
  TEMPLATE_STATUS_LABEL,
  TEMPLATE_STATUS_TONE,
  buildRequiredSemaphore,
} from '../whatsappData.js';
import styles from '../WhatsAppOnboarding.module.css';

const SEMAPHORE_TONE = { green: 'success', yellow: 'warning', red: 'danger' };

/**
 * Message-templates panel: the required-template semaphore, the new-template
 * form and the list of registered templates. Presentational — all state and
 * the mutation actions come from the `useWhatsAppData` hook via props.
 *
 * @param {{
 *   templates: Array<object>,
 *   templatesByPurpose: Record<string, Array<object>>,
 *   templateForm: object,
 *   isLoadingTemplates: boolean,
 *   isBusy: boolean,
 *   tenantId: string | undefined,
 *   onTemplateFormChange: (form: object) => void,
 *   onCreate: () => void,
 *   onSync: () => void,
 *   onDelete: (template: object) => void,
 * }} props
 */
export function TemplatesPanel({
  templates,
  templatesByPurpose,
  templateForm,
  isLoadingTemplates,
  isBusy,
  tenantId,
  onTemplateFormChange,
  onCreate,
  onSync,
  onDelete,
}) {
  const set = (key) => (event) =>
    onTemplateFormChange({ ...templateForm, [key]: event.target.value });

  // Local handlers keep the legacy names (handleCreateTemplate / handleSync /
  // handleDeleteTemplate) so the static tests can assert on the markup.
  const handleCreateTemplate = (event) => {
    event.preventDefault();
    onCreate();
  };
  const handleSyncTemplates = () => onSync();
  const handleDeleteTemplate = (template) => onDelete(template);

  const semaphore = buildRequiredSemaphore(templatesByPurpose);

  const columns = [
    {
      key: 'name',
      header: 'Nombre',
      accessor: (row) => (
        <div className={styles.templateCell}>
          <code>{row.name}</code>
          {row.rejection_reason ? (
            <span className={styles.templateReject}>{row.rejection_reason}</span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'purpose',
      header: 'Propósito',
      accessor: (row) =>
        TEMPLATE_PURPOSES.find((p) => p.id === row.purpose)?.label || row.purpose,
    },
    { key: 'category', header: 'Categoría', accessor: (row) => row.category },
    { key: 'locale', header: 'Idioma', accessor: (row) => row.locale },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => (
        <StatusBadge tone={TEMPLATE_STATUS_TONE[row.status] || 'neutral'}>
          {TEMPLATE_STATUS_LABEL[row.status] || row.status}
        </StatusBadge>
      ),
    },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) => (
        <button
          type="button"
          className={styles.secondaryButton}
          disabled={isBusy}
          onClick={() => handleDeleteTemplate(row)}
        >
          Eliminar
        </button>
      ),
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Plantillas de mensajes"
        subtitle="Las plantillas aprobadas por Meta son obligatorias para enviar mensajes fuera de la ventana de 24 h. Configura al menos confirmación de cita y recordatorio 24 h antes de salir a producción."
        actions={
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={isBusy || !tenantId}
            onClick={handleSyncTemplates}
          >
            Sincronizar estado con Meta
          </button>
        }
      />

      <div className={styles.semaphore} data-testid="templates-semaphore">
        {semaphore.map((item) => (
          <div key={item.id} className={styles.semaphoreCard}>
            <strong>{item.label}</strong>
            <StatusBadge tone={SEMAPHORE_TONE[item.tone] || 'neutral'}>{item.text}</StatusBadge>
          </div>
        ))}
      </div>

      <form className={styles.form} onSubmit={handleCreateTemplate}>
        <div className={styles.formRow}>
          <FormField label="Nombre (snake_case)">
            <input
              type="text"
              maxLength={512}
              value={templateForm.name}
              onChange={set('name')}
              placeholder="appointment_confirmation_es"
            />
          </FormField>
          <FormField label="Idioma">
            <input
              type="text"
              maxLength={5}
              value={templateForm.locale}
              onChange={set('locale')}
              placeholder="es"
            />
          </FormField>
        </div>
        <div className={styles.formRow}>
          <FormField label="Categoría">
            <select value={templateForm.category} onChange={set('category')}>
              <option value="utility">utility</option>
              <option value="marketing">marketing</option>
              <option value="authentication">authentication</option>
            </select>
          </FormField>
          <FormField label="Propósito">
            <select value={templateForm.purpose} onChange={set('purpose')}>
              {TEMPLATE_PURPOSES.map((purpose) => (
                <option key={purpose.id} value={purpose.id}>
                  {purpose.label}
                </option>
              ))}
            </select>
          </FormField>
        </div>
        <FormField label="Header (texto opcional)">
          <input
            type="text"
            value={templateForm.header}
            onChange={set('header')}
            placeholder="Recordatorio de cita"
          />
        </FormField>
        <FormField label="Body (usa variables {{1}}, {{2}}…)">
          <textarea
            rows={3}
            value={templateForm.body}
            onChange={set('body')}
            placeholder="Hola {{1}}, te recordamos tu cita el {{2}} a las {{3}}."
          />
        </FormField>
        <FormField label="Footer (opcional)">
          <input
            type="text"
            value={templateForm.footer}
            onChange={set('footer')}
            placeholder="Equipo de soporte"
          />
        </FormField>
        <FormField label="Botones (uno por línea, opcional)">
          <textarea
            rows={2}
            value={templateForm.buttons}
            onChange={set('buttons')}
            placeholder={'Confirmar\nReagendar'}
          />
        </FormField>
        <div className={styles.formActions}>
          <button
            type="submit"
            className={styles.primaryButton}
            disabled={isBusy || !tenantId}
          >
            Registrar plantilla
          </button>
        </div>
      </form>

      {isLoadingTemplates ? (
        <p className={styles.hint}>Cargando plantillas…</p>
      ) : templates.length === 0 ? (
        <EmptyState
          title="Sin plantillas"
          description="Aún no hay plantillas registradas. Crea la primera con el formulario de arriba."
        />
      ) : (
        <DataTable
          caption="Plantillas de WhatsApp del tenant"
          columns={columns}
          rows={templates}
          rowKey={(row) => row.id}
        />
      )}
    </Card>
  );
}
