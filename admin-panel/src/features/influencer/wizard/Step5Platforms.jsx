/**
 * UI-INFLU-012 — Wizard Paso 5: Plataformas.
 *
 * Refactor visual UI-INFLU-014.12: shell alineado con Step1Face.
 */
import { useState } from 'react';

import { AlertBanner } from '../../../components/ui/index.js';
import styles from '../_shared/RavitStyles.module.css';
import {
  MODES,
  PLATFORMS,
  cannotDisableDiscloseAi,
  computeWeeklyCredits,
  validateAtLeastOnePlatform,
} from './step5PlatformsData.js';
import { WizardStepper } from './WizardStepper.jsx';


const STEPS = [
  { key: 'face', label: 'Cara', description: 'Rasgos visuales', status: 'done' },
  { key: 'body', label: 'Cuerpo', description: 'Constitución', status: 'done' },
  { key: 'identity', label: 'Identidad', description: 'Nombre y mundo', status: 'done' },
  { key: 'voice', label: 'Voz', description: 'Tono y carácter', status: 'done' },
  { key: 'platforms', label: 'Plataformas', description: 'Dónde publica', status: 'current' },
];


export function Step5Platforms({
  initialAccounts = [],
  initialMode = 'manual_approval',
  initialAutoRespondDms = false,
  pricing,
  onConnectInstagram,
  onActivate,
  onSaveDraft, // eslint-disable-line no-unused-vars
  onBack,
}) {
  const [accounts, setAccounts] = useState(initialAccounts);
  const [mode, setMode] = useState(initialMode);
  const [autoRespondDms, setAutoRespondDms] = useState(initialAutoRespondDms);
  const [error, setError] = useState(null);

  const togglePlatform = (platform) => {
    setAccounts((prev) => {
      const existing = prev.find((a) => a.platform === platform);
      if (existing) return prev.filter((a) => a.platform !== platform);
      return [...prev, { platform, handle: '', posts_per_week: 3, primary_kind: 'photo' }];
    });
  };

  const updateAccount = (platform, key, value) => {
    setAccounts((prev) => prev.map((a) => a.platform === platform ? { ...a, [key]: value } : a));
  };

  const handleConnect = (platform) => {
    if (platform === 'instagram') {
      onConnectInstagram?.();
    }
  };

  const weeklyCredits = computeWeeklyCredits(accounts, pricing);
  const totalPosts = accounts.reduce((acc, a) => acc + Number(a.posts_per_week || 0), 0);

  const handleActivate = () => {
    if (!validateAtLeastOnePlatform(accounts)) {
      setError('Conecta al menos una plataforma con un handle.');
      return;
    }
    setError(null);
    onActivate?.({
      accounts: accounts.map((a) => ({
        platform: a.platform,
        handle: a.handle,
        posts_per_week: Number(a.posts_per_week) || 3,
      })),
      mode,
      auto_respond_dms: autoRespondDms,
      disclose_ai: true,  // Enforcer — el frontend NO permite cambiarlo.
    });
  };

  return (
    <div className={styles.page} data-module="influencer" data-view="wizard-step-5">
      {onBack ? (
        <div style={{ marginBottom: 12 }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--ravit-text-muted, #6b7280)', fontSize: 13,
              padding: '4px 0',
            }}
          >
            ← Casting
          </button>
        </div>
      ) : null}

      <div className={styles.pageHeader}>
        <div className={styles.eyebrow}>CASTING / NUEVO PERSONAJE</div>
        <h1 className={styles.h1Page}>Dónde vive</h1>
        <p className={styles.textSubtle}>
          Conecta sus plataformas y elige cadencia. Al activarlo empieza
          a publicar según el modo seleccionado.
        </p>
      </div>

      <div style={{ marginTop: 16, marginBottom: 24 }}>
        <WizardStepper steps={STEPS} />
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <ul aria-label="Lista de plataformas" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {PLATFORMS.map((p) => {
            const account = accounts.find((a) => a.platform === p.value);
            const isConnected = !!account?.handle;
            return (
              <li key={p.value} style={{
                display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                padding: 'var(--space-2) 0',
                borderBottom: '1px solid rgba(27, 37, 66, 0.06)',
              }}>
                <div style={{ flex: 1, fontWeight: 600 }}>{p.label}</div>
                {account ? (
                  <>
                    <input
                      placeholder="@handle"
                      value={account.handle}
                      onChange={(e) => updateAccount(p.value, 'handle', e.target.value)}
                      aria-label={`Handle de ${p.label}`}
                      style={{
                        padding: '6px 10px', borderRadius: 8,
                        border: '1px solid #e6e0d4',
                      }}
                    />
                    <input
                      type="number"
                      min="0"
                      max="50"
                      value={account.posts_per_week}
                      onChange={(e) => updateAccount(p.value, 'posts_per_week', Number(e.target.value))}
                      aria-label={`Posts por semana en ${p.label}`}
                      style={{
                        width: 70, padding: '6px 10px',
                        borderRadius: 8, border: '1px solid #e6e0d4',
                      }}
                    />
                    <span style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>/sem</span>
                    <button
                      type="button"
                      onClick={() => togglePlatform(p.value)}
                      style={{
                        padding: '6px 14px', borderRadius: 8,
                        border: '1px solid #e6e0d4', background: '#fff',
                        cursor: 'pointer', fontSize: 13,
                      }}
                    >
                      Quitar
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={!p.available}
                    onClick={() => {
                      togglePlatform(p.value);
                      handleConnect(p.value);
                    }}
                    title={p.available ? undefined : 'Próximamente'}
                    style={{
                      padding: '6px 14px', borderRadius: 8,
                      border: p.available ? '1.5px solid #2DBB6A' : '1px solid #e6e0d4',
                      background: p.available ? '#eaf7ef' : '#f3f3ee',
                      color: p.available ? '#1b6f3e' : 'var(--color-text-subtle, #6b7280)',
                      cursor: p.available ? 'pointer' : 'not-allowed',
                      fontSize: 13, fontWeight: 600,
                    }}
                  >
                    {p.available ? 'Conectar' : 'Próximamente'}
                  </button>
                )}
                {isConnected && (
                  <span aria-label="Estado" style={{ fontSize: 11, color: '#0F7A3F' }}>
                    Conectada
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600 }}>Modo de publicación</legend>
          {MODES.map((m) => (
            <label key={m.value} style={{ display: 'block', marginTop: 'var(--space-1)' }}>
              <input
                type="radio"
                name="mode"
                value={m.value}
                checked={mode === m.value}
                onChange={() => setMode(m.value)}
              />
              <span style={{ marginLeft: 'var(--space-1)' }}>{m.label}</span>
            </label>
          ))}
        </fieldset>

        <label style={{ display: 'block', marginTop: 'var(--space-3)' }}>
          <input
            type="checkbox"
            checked={autoRespondDms}
            onChange={(e) => setAutoRespondDms(e.target.checked)}
          />
          <span style={{ marginLeft: 'var(--space-1)' }}>Auto-responder DMs (solo preguntas frecuentes)</span>
        </label>

        <label style={{ display: 'block', marginTop: 'var(--space-2)' }} title="No se puede desactivar — política de transparencia con tu audiencia.">
          <input
            type="checkbox"
            checked
            disabled={cannotDisableDiscloseAi()}
            aria-label="Etiqueta IA visible"
          />
          <span style={{ marginLeft: 'var(--space-1)' }}>
            Etiqueta IA visible (recomendado · transparencia con tu audiencia)
          </span>
        </label>
      </div>

      <div className={styles.card} style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ fontWeight: 600 }}>Recap</div>
        <div style={{ fontSize: 14, color: 'var(--color-text-subtle, #6b7280)', marginTop: 'var(--space-1)' }}>
          Cadencia · <strong>{totalPosts} posts / semana</strong> · ≈
          <strong style={{ marginLeft: 4 }}>{weeklyCredits} créditos/semana</strong>
        </div>
      </div>

      {error && <AlertBanner tone="warning" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>}

      <div style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        gap: 16, marginTop: 32, paddingTop: 16, borderTop: '1px solid #eee9dc',
      }}>
        <span className={styles.textSubtle} style={{ fontSize: 13 }}>Paso 5 de 5</span>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={handleActivate}
        >
          Crear personaje
        </button>
      </div>
    </div>
  );
}
