/**
 * UI-INFLU-013 — Generar contenido (composer).
 */
import { useState } from 'react';

import { AlertBanner, Card, PageHeader } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';
import { NoCreditsEmpty, ProviderUnavailableEmpty } from '../components/empty/index.js';
import {
  KINDS,
  PROMPT_MAX,
  buildGeneratePayload,
  computeCost,
  costExceedsBalance,
  formatsForKind,
  kindMeta,
  promptWithinLimit,
} from './generateData.js';


export function Generate({
  balance = 0,
  recentGenerations = [],
  providerDown = false,
  onGenerate,
  onTopUp,
  onRetryProvider,
  onSchedulePost,
}) {
  const [form, setForm] = useState({
    kind: 'photo', prompt: '', format: '1:1', count: 1,
    style: '', location: '', reference_image_url: '', safety_mode: true,
  });
  const [error, setError] = useState(null);
  const { can } = usePermissions();
  const canGenerate = can('influencer.generate');

  const update = (key, value) => setForm((p) => ({ ...p, [key]: value }));

  const setKind = (kind) => {
    const validFormat = formatsForKind(kind)[0];
    setForm((p) => ({ ...p, kind, format: validFormat || '1:1' }));
  };

  const totalCost = computeCost(form.kind, form.count);
  const overBudget = costExceedsBalance(form.kind, form.count, balance);

  const handleSubmit = async () => {
    if (!canGenerate) { setError('No tienes permiso para generar contenido.'); return; }
    if (overBudget) { setError('Balance insuficiente.'); return; }
    if (!promptWithinLimit(form.prompt)) {
      setError(`El prompt excede ${PROMPT_MAX} caracteres.`);
      return;
    }
    setError(null);
    await onGenerate?.(buildGeneratePayload(form));
  };

  if (providerDown) {
    return <ProviderUnavailableEmpty onRetry={onRetryProvider} />;
  }
  if (balance <= 0) {
    return <NoCreditsEmpty onTopUp={onTopUp} />;
  }

  return (
    <div data-module="influencer" data-view="generate">
      <PageHeader eyebrow="Ravit Studio" title="Generar contenido" description={`Balance: ${balance} créditos`} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 'var(--space-3)' }}>
        <div>
          <Card padding="md">
            <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Tipo</div>
            <ul aria-label="Tipo de contenido" style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
              gap: 'var(--space-2)', margin: 0, padding: 0, listStyle: 'none',
            }}>
              {KINDS.map((k) => {
                const active = form.kind === k.value;
                return (
                  <li key={k.value}>
                    <button
                      type="button"
                      onClick={() => setKind(k.value)}
                      aria-pressed={active}
                      style={{
                        width: '100%',
                        padding: 'var(--space-2)',
                        border: active ? '2px solid var(--color-action-primary-bg, #111)' : '1px solid var(--color-border, #d1d5db)',
                        borderRadius: 'var(--radius-md, 6px)',
                        background: 'transparent',
                        cursor: 'pointer',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontWeight: 700 }}>{k.label}</div>
                      <div style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>{k.cost} créditos</div>
                      {k.badge && (
                        <span style={{
                          display: 'inline-block', marginTop: 4, fontSize: 10,
                          padding: '1px 6px', borderRadius: 999,
                          background: 'var(--color-warning-bg, #fef3c7)',
                          color: 'var(--color-warning-fg, #92400e)',
                        }}>{k.badge}</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
            <label style={{ display: 'block' }}>
              <span style={{ fontWeight: 600 }}>Prompt ({form.prompt.length}/{PROMPT_MAX})</span>
              <textarea
                rows={4}
                value={form.prompt}
                onChange={(e) => update('prompt', e.target.value.slice(0, PROMPT_MAX))}
                style={{ width: '100%' }}
                aria-label="Prompt"
              />
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
              <label>
                <span style={{ fontSize: 12 }}>Formato</span>
                <select
                  value={form.format}
                  onChange={(e) => update('format', e.target.value)}
                  aria-label="Formato"
                >
                  {formatsForKind(form.kind).map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </label>
              <label>
                <span style={{ fontSize: 12 }}>Cantidad</span>
                <input
                  type="number" min="1" max="10"
                  value={form.count}
                  onChange={(e) => update('count', Number(e.target.value))}
                  aria-label="Cantidad"
                />
              </label>
            </div>

            <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
              <input
                type="checkbox"
                checked={form.safety_mode}
                onChange={(e) => update('safety_mode', e.target.checked)}
              />
              <span style={{ marginLeft: 'var(--space-1)' }}>Modo seguro (SFW + brand safety)</span>
            </label>
          </Card>

          {error && <AlertBanner tone="warn" style={{ marginTop: 'var(--space-3)' }}>{error}</AlertBanner>}

          <div style={{ marginTop: 'var(--space-3)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canGenerate || overBudget}
              title={
                !canGenerate ? 'No tienes permiso de generación' :
                overBudget ? `Necesitas ${totalCost - balance} créditos más` :
                undefined
              }
            >
              Generar · {form.count} {form.count === 1 ? 'asset' : 'assets'} · {totalCost} créditos
            </button>
            <span style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>
              {kindMeta(form.kind)?.cost} créditos / asset
            </span>
          </div>
        </div>

        <aside aria-label="Cola de generaciones">
          <Card padding="md">
            <div style={{ fontWeight: 600 }}>Últimas generaciones</div>
            {recentGenerations.length === 0 ? (
              <p style={{ color: 'var(--color-text-subtle, #6b7280)' }}>
                Aún no has generado nada con este personaje.
              </p>
            ) : (
              <ul aria-label="Generations queue" style={{
                display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
                margin: 0, padding: 0, listStyle: 'none',
              }}>
                {recentGenerations.map((g) => (
                  <li key={g.id} style={{
                    padding: 'var(--space-2)',
                    border: '1px solid var(--color-border-subtle, #e5e7eb)',
                    borderRadius: 'var(--radius-md, 6px)',
                  }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{g.kind}</div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)' }}>
                      {g.status}
                    </div>
                    {g.status === 'succeeded' && (
                      <button
                        type="button"
                        onClick={() => onSchedulePost?.(g)}
                        style={{ marginTop: 4 }}
                      >Programar post</button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </aside>
      </div>
    </div>
  );
}
