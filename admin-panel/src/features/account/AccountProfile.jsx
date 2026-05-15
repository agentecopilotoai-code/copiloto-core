import { useMemo, useState } from 'react';

import { AlertBanner, FormField, PageHeader } from '../../components/ui/index.js';
import { useAuth } from '../../context/AuthContext.jsx';
import styles from './Account.module.css';
import {
  ACCOUNT_LOCALES,
  ACCOUNT_TIMEZONES,
  deriveProfileForm,
  profileDisplayName,
  profileInitials,
  profileRoleLabel,
} from './accountData.js';

/**
 * UI-016.7 — `/account/profile`.
 *
 * Form de perfil del usuario (nombre, teléfono, idioma, timezone). El email
 * está disabled porque lo gestiona Auth0 — copy del HTML T3:
 * "Lo gestiona Auth0 · cambia desde tu identity provider". El nombre que
 * mostramos en el hero viene de `session.profile.name`/`email` (Auth0).
 *
 * Mientras `PATCH /v1/me/profile` (UI-016.7-FU) no exista, "Guardar cambios"
 * dispara un `AlertBanner tone="warning"` explicando el estado del feature —
 * mismo patrón que UI-016.1 con "Marcar live".
 */
export function AccountProfile() {
  const { session } = useAuth();
  const profile = session?.profile ?? null;

  const initialForm = useMemo(() => deriveProfileForm(profile), [profile]);
  const [form, setForm] = useState(initialForm);
  const [notice, setNotice] = useState(null);

  const onChange = (field) => (event) => {
    const value = event.target.value;
    setForm((current) => ({ ...current, [field]: value }));
    setNotice(null);
  };

  const onSubmit = (event) => {
    event.preventDefault();
    setNotice('saved');
  };

  return (
    <section className={styles.section}>
      <PageHeader
        eyebrow="Cuenta · perfil"
        title="Perfil"
        description="Tus datos personales y preferencias de localización para este tenant. Auth0 gestiona la identidad (nombre / email); el resto vive en CopilotoIA."
      />

      <div className={styles.profileHero}>
        <span className={styles.profileAvatar} aria-hidden="true">
          {profile?.picture ? (
            <img alt="" src={profile.picture} />
          ) : (
            profileInitials(profile)
          )}
        </span>
        <div className={styles.profileMeta}>
          <p className={styles.profileName}>{profileDisplayName(profile)}</p>
          <p className={styles.profileSubmeta}>
            {form.email || '—'} · miembro desde feb 2025
          </p>
        </div>
        <span className={styles.profileBadge}>{profileRoleLabel(profile)}</span>
      </div>

      {notice === 'saved' ? (
        <AlertBanner
          tone="warning"
          title="Tus cambios todavía no se persisten"
          action={
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => setNotice(null)}
            >
              Entendido
            </button>
          }
        >
          El endpoint <code>PATCH /v1/me/profile</code> está pendiente
          (<strong>UI-016.7-FU</strong>). Por ahora puedes editar el formulario
          y validarlo visualmente, pero los cambios se aplicarán al backend
          cuando ese endpoint exista.
        </AlertBanner>
      ) : null}

      <form className={styles.form} onSubmit={onSubmit}>
        <FormField
          label="Nombre completo"
          hint="Lo verán tus clientes y compañeros en handoffs."
          value={form.name}
          onChange={onChange('name')}
          autoComplete="name"
        />

        <FormField
          label="Email"
          hint="Lo gestiona Auth0 · cambia desde tu identity provider"
          value={form.email}
          readOnly
          aria-readonly="true"
          autoComplete="email"
        />

        <FormField
          label="Teléfono"
          hint="Para 2FA y avisos urgentes."
          value={form.phone}
          onChange={onChange('phone')}
          autoComplete="tel"
          placeholder="+57 300 8842 100"
        />

        <div className={styles.formRow}>
          <FormField label="Idioma de la interfaz">
            <select value={form.locale} onChange={onChange('locale')}>
              {ACCOUNT_LOCALES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Zona horaria">
            <select value={form.timezone} onChange={onChange('timezone')}>
              {ACCOUNT_TIMEZONES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FormField>
        </div>

        <div className={styles.formActions}>
          <button type="submit" className={styles.primaryButton}>
            Guardar cambios
          </button>
        </div>
      </form>
    </section>
  );
}
