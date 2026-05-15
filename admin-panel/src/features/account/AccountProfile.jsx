import { useCallback, useEffect, useMemo, useState } from 'react';

import { AlertBanner, FormField, PageHeader, useToast } from '../../components/ui/index.js';
import { useAuth } from '../../context/AuthContext.jsx';
import { getMyProfile, patchMyProfile } from '../../services/coreApi.js';
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
 * UI-016.7-FU cableó los endpoints reales: GET `/v1/me/profile` hidrata el
 * form con los valores cacheados en `app.user_preferences` (con fallback al
 * profile de Auth0); PATCH persiste los cambios y dispara un toast `success`
 * (4s, patrón UI-016.5). Errores 4xx muestran un `AlertBanner tone="danger"`
 * con el detail del backend; 5xx caen al toast `error` (8s).
 */
export function AccountProfile() {
  const { session } = useAuth();
  const profile = session?.profile ?? null;
  const toast = useToast();

  const initialForm = useMemo(() => deriveProfileForm(profile), [profile]);
  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // UI-016.7-FU: hidrata el form con los datos persistidos del backend cuando
  // están disponibles. Si el GET falla (404 antes de la primera escritura,
  // 401 sin sesión válida, etc.) seguimos usando el initialForm derivado del
  // profile de Auth0 — el form sigue editable y un POST creará la fila.
  useEffect(() => {
    let cancelled = false;
    if (!session) return undefined;
    (async () => {
      try {
        const data = await getMyProfile(session);
        if (cancelled) return;
        setForm((current) => ({
          ...current,
          name: data.display_name || current.name,
          email: data.email || current.email,
          phone: data.phone || current.phone,
          locale: data.locale || current.locale,
          timezone: data.timezone || current.timezone,
        }));
      } catch {
        // Tolerable: caer al fallback derivado del profile de Auth0.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session]);

  const onChange = (field) => (event) => {
    const value = event.target.value;
    setForm((current) => ({ ...current, [field]: value }));
    setError(null);
  };

  const onSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      if (saving || !session) return;
      setSaving(true);
      setError(null);
      const payload = {
        display_name: form.name?.trim() || null,
        phone: form.phone?.trim() || null,
        locale: form.locale || null,
        timezone: form.timezone || null,
      };
      try {
        await patchMyProfile(session, payload);
        toast.success('Perfil actualizado.');
      } catch (err) {
        if (err?.status && err.status >= 400 && err.status < 500) {
          setError(err?.message || 'No se pudo guardar el perfil.');
        } else {
          toast.error(err?.message || 'Error inesperado al guardar.');
        }
      } finally {
        setSaving(false);
      }
    },
    [saving, session, form, toast],
  );

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

      {error ? (
        <AlertBanner
          tone="danger"
          title="No se pudo guardar el perfil"
          action={
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => setError(null)}
            >
              Cerrar
            </button>
          }
        >
          {error}
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
          <button type="submit" className={styles.primaryButton} disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </form>
    </section>
  );
}
