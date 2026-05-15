import { Button, Card, FormField } from '../../../../components/ui/index.js';
import { COUNTRY_PROFILES, SUPPORTED_COUNTRIES, availableStatusTransitions } from '../tenantSetupData.js';
import { slugifyVertical } from '../tenantSetupTransforms.js';
import styles from '../TenantSetupWizard.module.css';

export function GeneralTab({ state, actions }) {
  const {
    currentTenantId,
    tenantForm,
    settingsForm,
    isBusy,
    contactTags,
    tagForm,
    editingTagId,
    tenantStatus,
    targetStatus,
    statusReason,
  } = state;
  const {
    setTenantForm,
    setSettingsForm,
    handleSaveTenant,
    handleSaveTag,
    handleDeleteTag,
    startEditingTag,
    cancelEditingTag,
    setTagForm,
    handleChangeStatus,
    setTargetStatus,
    setStatusReason,
  } = actions;

  return (
    <>
      <Card padding="md">
        <form className={styles.formGrid} onSubmit={handleSaveTenant}>
          <FormField label="Slug">
            <input
              value={tenantForm.slug}
              onChange={(event) => setTenantForm({ ...tenantForm, slug: event.target.value })}
              required
            />
          </FormField>
          <FormField label="Razón social">
            <input
              value={tenantForm.legal_name}
              onChange={(event) => setTenantForm({ ...tenantForm, legal_name: event.target.value })}
              required
            />
          </FormField>
          <FormField label="Nombre visible">
            <input
              value={tenantForm.display_name}
              onChange={(event) => setTenantForm({ ...tenantForm, display_name: event.target.value })}
              required
            />
          </FormField>
          <FormField label="Tipo de negocio">
            <input
              placeholder="Ej. Clínica dental, Spa, Taller mecánico"
              value={tenantForm.business_type_label}
              onChange={(event) => {
                const label = event.target.value;
                setTenantForm({
                  ...tenantForm,
                  business_type_label: label,
                  vertical_code: tenantForm.vertical_code || slugifyVertical(label),
                });
              }}
              maxLength={160}
              required
            />
          </FormField>
          <FormField label="Clave técnica (vertical_code)">
            <input
              placeholder="Ej. dental, spa, taller"
              value={tenantForm.vertical_code}
              onChange={(event) => setTenantForm({ ...tenantForm, vertical_code: event.target.value })}
              maxLength={64}
              required
            />
          </FormField>
          {/* TASK-0073: selector cerrado al catálogo soportado. */}
          <FormField label="País">
            <select
              value={tenantForm.country_code}
              onChange={(event) => {
                const next = event.target.value;
                const profile = COUNTRY_PROFILES[next] || COUNTRY_PROFILES.CO;
                setTenantForm({
                  ...tenantForm,
                  country_code: next,
                  timezone: profile.timezone,
                });
                setSettingsForm({ ...settingsForm, locale: profile.locale });
              }}
              required
            >
              {SUPPORTED_COUNTRIES.map((code) => (
                <option key={code} value={code}>
                  {COUNTRY_PROFILES[code].label} ({COUNTRY_PROFILES[code].currency})
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Zona horaria">
            <input
              value={tenantForm.timezone}
              onChange={(event) => setTenantForm({ ...tenantForm, timezone: event.target.value })}
              required
            />
          </FormField>
          <div className={styles.actions}>
            <Button variant="primary" type="submit" disabled={isBusy}>
              {currentTenantId ? 'Actualizar tenant' : 'Crear tenant'}
            </Button>
          </div>
        </form>
      </Card>

      {currentTenantId ? (
        <Card padding="md">
          <h3 className={styles.sectionTitle}>Etiquetas de contacto</h3>
          <p className={styles.hint}>
            Define las etiquetas disponibles para clasificar contactos del CRM (ej. VIP, Nuevo, En tratamiento).
          </p>
          <form className={styles.formGrid} onSubmit={handleSaveTag}>
            <FormField label="Nombre">
              <input
                value={tagForm.name}
                onChange={(event) => setTagForm({ ...tagForm, name: event.target.value })}
                maxLength={80}
                placeholder="Ej. VIP"
                required
              />
            </FormField>
            <FormField label="Color">
              <input
                type="color"
                value={tagForm.color}
                onChange={(event) => setTagForm({ ...tagForm, color: event.target.value })}
              />
            </FormField>
            <FormField label="Descripción" className={styles.wide}>
              <input
                value={tagForm.description}
                onChange={(event) => setTagForm({ ...tagForm, description: event.target.value })}
                maxLength={500}
                placeholder="Opcional"
              />
            </FormField>
            <div className={styles.actions}>
              <Button variant="primary" type="submit" disabled={isBusy || !tagForm.name.trim()}>
                {editingTagId ? 'Actualizar etiqueta' : 'Crear etiqueta'}
              </Button>
              {editingTagId ? (
                <Button variant="secondary" type="button" onClick={cancelEditingTag}>
                  Cancelar edición
                </Button>
              ) : null}
            </div>
          </form>
          {contactTags.length ? (
            <ul className={styles.tagList}>
              {contactTags.map((tag) => (
                <li key={tag.id} className={styles.tagRow}>
                  <span
                    className={styles.tagPill}
                    style={tag.color ? { background: tag.color } : undefined}
                  >
                    {tag.name}
                  </span>
                  <span className={styles.tagDesc}>{tag.description || '—'}</span>
                  <span className={styles.hint}>{tag.contacts_count ?? 0} contactos</span>
                  <Button variant="secondary" size="sm" type="button" onClick={() => startEditingTag(tag)}>
                    Editar
                  </Button>
                  <Button variant="secondary" size="sm" type="button" onClick={() => handleDeleteTag(tag.id)}>
                    Eliminar
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.hint}>Aún no hay etiquetas configuradas.</p>
          )}
        </Card>
      ) : null}

      {currentTenantId && tenantStatus ? (
        <Card padding="md">
          <h3 className={styles.sectionTitle}>Estado del tenant</h3>
          <p className={styles.hint}>
            Estado actual:{' '}
            <span className={`status-badge status-${tenantStatus}`}>{tenantStatus}</span>
          </p>
          <p className={styles.hint}>
            {tenantStatus === 'trial' && 'El tenant está en trial. Actívalo cuando cumpla los prerrequisitos de go-live.'}
            {tenantStatus === 'active' && 'Tenant activo y operando en producción.'}
            {tenantStatus === 'suspended' && 'Tenant suspendido temporalmente. Puedes reactivarlo cuando el problema esté resuelto.'}
            {tenantStatus === 'churned' && 'Tenant dado de baja definitivamente. No se puede transicionar a otro estado.'}
          </p>
          {(availableStatusTransitions[tenantStatus] || []).length > 0 ? (
            <form className={styles.formGrid} onSubmit={handleChangeStatus}>
              <FormField label="Nuevo estado">
                <select value={targetStatus} onChange={(e) => setTargetStatus(e.target.value)}>
                  {availableStatusTransitions[tenantStatus].map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Razón (obligatoria)" className={styles.wide}>
                <input
                  placeholder="Ej: Prerrequisitos verificados, aprobado para go-live"
                  required
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                />
              </FormField>
              <div className={styles.actions}>
                <Button variant="primary" type="submit" disabled={isBusy || !statusReason.trim()}>
                  Cambiar estado
                </Button>
              </div>
            </form>
          ) : null}
        </Card>
      ) : null}
    </>
  );
}
