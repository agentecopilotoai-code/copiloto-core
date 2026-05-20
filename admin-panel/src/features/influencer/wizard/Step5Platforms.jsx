/**
 * UI-INFLU-012 — Wizard Paso 5: Plataformas.
 */
import { useState } from 'react';

import { AlertBanner, Card, PageHeader, Stepper } from '../../../components/ui/index.js';
import {
  MODES,
  PLATFORMS,
  cannotDisableDiscloseAi,
  computeWeeklyCredits,
  validateAtLeastOnePlatform,
} from './step5PlatformsData.js';


const STEPS = [
  { id: 'face', label: 'Cara', state: 'complete' },
  { id: 'body', label: 'Cuerpo', state: 'complete' },
  { id: 'identity', label: 'Identidad', state: 'complete' },
  { id: 'voice', label: 'Voz', state: 'complete' },
  { id: 'platforms', label: 'Plataformas', state: 'current' },
];


export function Step5Platforms({
  initialAccounts = [],
  initialMode = 'manual_approval',
  initialAutoRespondDms = false,
  pricing,
  onConnectInstagram,
  onActivate,
  onSaveDraft,
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
    <div data-module="influencer" data-view="wizard-step-5">
      <PageHeader eyebrow="Crear personaje · Paso 5 de 5" title="Plataformas" />
      <Stepper steps={STEPS} />

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <ul aria-label="Lista de plataformas" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {PLATFORMS.map((p) => {
            const account = accounts.find((a) => a.platform === p.value);
            const isConnected = !!account?.handle;
            return (
              <li key={p.value} style={{
                display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                padding: 'var(--space-2) 0',
                borderBottom: '1px solid var(--color-border-subtle, #e5e7eb)',
              }}>
                <div style={{ flex: 1, fontWeight: 600 }}>{p.label}</div>
                {account ? (
                  <>
                    <input
                      placeholder="@handle"
                      value={account.handle}
                      onChange={(e) => updateAccount(p.value, 'handle', e.target.value)}
                      aria-label={`Handle de ${p.label}`}
                    />
                    <input
                      type="number"
                      min="0"
                      max="50"
                      value={account.posts_per_week}
                      onChange={(e) => updateAccount(p.value, 'posts_per_week', Number(e.target.value))}
                      aria-label={`Posts por semana en ${p.label}`}
                      style={{ width: 70 }}
                    />
                    <span style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>/sem</span>
                    <button type="button" onClick={() => togglePlatform(p.value)}>Quitar</button>
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
                  >
                    {p.available ? 'Conectar' : 'Próximamente'}
                  </button>
                )}
                {isConnected && (
                  <span aria-label="Estado" style={{ fontSize: 11, color: 'var(--color-success-fg, #047857)' }}>
                    Conectada
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <fieldset>
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
      </Card>

      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ fontWeight: 600 }}>Recap</div>
        <div style={{ fontSize: 14, color: 'var(--color-text-subtle, #6b7280)', marginTop: 'var(--space-1)' }}>
          Cadencia · <strong>{totalPosts} posts / semana</strong> · ≈
          <strong style={{ marginLeft: 4 }}>{weeklyCredits} créditos/semana</strong>
        </div>
      </Card>

      {error && <AlertBanner tone="warn" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>}

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 'var(--space-4)',
      }}>
        <span>Paso 5 de 5</span>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button type="button" onClick={() => onSaveDraft?.({ accounts, mode, auto_respond_dms: autoRespondDms })}>
            Guardar borrador
          </button>
          <button type="button" onClick={handleActivate}>Crear personaje</button>
        </div>
      </div>
    </div>
  );
}
