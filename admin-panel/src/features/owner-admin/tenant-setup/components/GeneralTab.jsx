import { COUNTRY_PROFILES, SUPPORTED_COUNTRIES, availableStatusTransitions } from '../tenantSetupData.js';
import { slugifyVertical } from '../tenantSetupTransforms.js';

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
      <form className="wizard-panel form-grid" onSubmit={handleSaveTenant}>
        <label>
          Slug
          <input value={tenantForm.slug} onChange={(event) => setTenantForm({ ...tenantForm, slug: event.target.value })} required />
        </label>
        <label>
          Razón social
          <input value={tenantForm.legal_name} onChange={(event) => setTenantForm({ ...tenantForm, legal_name: event.target.value })} required />
        </label>
        <label>
          Nombre visible
          <input value={tenantForm.display_name} onChange={(event) => setTenantForm({ ...tenantForm, display_name: event.target.value })} required />
        </label>
        <label>
          Tipo de negocio
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
        </label>
        <label>
          Clave técnica (vertical_code)
          <input
            placeholder="Ej. dental, spa, taller"
            value={tenantForm.vertical_code}
            onChange={(event) => setTenantForm({ ...tenantForm, vertical_code: event.target.value })}
            maxLength={64}
            required
          />
        </label>
        <label>
          País
          {/* TASK-0073: selector cerrado al catálogo soportado.  Cambiar el
              país preselecciona timezone y locale por defecto. */}
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
        </label>
        <label>
          Zona horaria
          <input value={tenantForm.timezone} onChange={(event) => setTenantForm({ ...tenantForm, timezone: event.target.value })} required />
        </label>
        <div className="form-actions">
          <button className="primary-action" disabled={isBusy} type="submit">{currentTenantId ? 'Actualizar tenant' : 'Crear tenant'}</button>
        </div>
      </form>

      {currentTenantId ? (
        <div className="wizard-panel">
          <h3>Etiquetas de contacto</h3>
          <p className="hint">
            Define las etiquetas disponibles para clasificar contactos del CRM (ej. VIP, Nuevo, En tratamiento).
          </p>
          <form className="form-grid" onSubmit={handleSaveTag}>
            <label>
              Nombre
              <input
                value={tagForm.name}
                onChange={(event) => setTagForm({ ...tagForm, name: event.target.value })}
                maxLength={80}
                placeholder="Ej. VIP"
                required
              />
            </label>
            <label>
              Color
              <input
                type="color"
                value={tagForm.color}
                onChange={(event) => setTagForm({ ...tagForm, color: event.target.value })}
              />
            </label>
            <label className="wide">
              Descripción
              <input
                value={tagForm.description}
                onChange={(event) => setTagForm({ ...tagForm, description: event.target.value })}
                maxLength={500}
                placeholder="Opcional"
              />
            </label>
            <div className="form-actions">
              <button className="primary-action" type="submit" disabled={isBusy || !tagForm.name.trim()}>
                {editingTagId ? 'Actualizar etiqueta' : 'Crear etiqueta'}
              </button>
              {editingTagId ? (
                <button className="secondary-action" type="button" onClick={cancelEditingTag}>
                  Cancelar edición
                </button>
              ) : null}
            </div>
          </form>
          {contactTags.length ? (
            <ul style={{ listStyle: 'none', padding: 0, marginTop: '1rem' }}>
              {contactTags.map((tag) => (
                <li
                  key={tag.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    padding: '0.4rem 0',
                    borderBottom: '1px solid var(--border, #e2e8f0)',
                  }}
                >
                  <span
                    className="status-pill"
                    style={{ background: tag.color || '#4f6ef7', color: '#fff', padding: '0.15rem 0.6rem' }}
                  >
                    {tag.name}
                  </span>
                  <span className="hint" style={{ flex: 1 }}>{tag.description || '—'}</span>
                  <span className="hint">{tag.contacts_count ?? 0} contactos</span>
                  <button className="secondary-action" type="button" onClick={() => startEditingTag(tag)}>
                    Editar
                  </button>
                  <button className="secondary-action" type="button" onClick={() => handleDeleteTag(tag.id)}>
                    Eliminar
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">Aún no hay etiquetas configuradas.</p>
          )}
        </div>
      ) : null}

      {currentTenantId && tenantStatus ? (
        <div className="wizard-panel status-panel">
          <h3>Estado del tenant</h3>
          <div className="status-current">
            <span>Estado actual:</span>
            <span className={`status-badge status-${tenantStatus}`}>{tenantStatus}</span>
          </div>
          <p className="hint">
            {tenantStatus === 'trial' && 'El tenant está en trial. Actívalo cuando cumpla los prerrequisitos de go-live.'}
            {tenantStatus === 'active' && 'Tenant activo y operando en producción.'}
            {tenantStatus === 'suspended' && 'Tenant suspendido temporalmente. Puedes reactivarlo cuando el problema esté resuelto.'}
            {tenantStatus === 'churned' && 'Tenant dado de baja definitivamente. No se puede transicionar a otro estado.'}
          </p>
          {(availableStatusTransitions[tenantStatus] || []).length > 0 ? (
            <form className="form-grid" onSubmit={handleChangeStatus}>
              <label>
                Nuevo estado
                <select value={targetStatus} onChange={(e) => setTargetStatus(e.target.value)}>
                  {availableStatusTransitions[tenantStatus].map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </label>
              <label className="wide">
                Razón (obligatoria)
                <input
                  placeholder="Ej: Prerrequisitos verificados, aprobado para go-live"
                  required
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                />
              </label>
              <div className="form-actions">
                <button className="primary-action" disabled={isBusy || !statusReason.trim()} type="submit">Cambiar estado</button>
              </div>
            </form>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
