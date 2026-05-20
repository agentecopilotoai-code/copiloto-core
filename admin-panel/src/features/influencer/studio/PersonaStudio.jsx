/**
 * UI-INFLU-005 — Estudio del personaje (detalle).
 *
 * Consume el bundle `GET /v1/influencer/personas/{id}/studio` y monta
 * 6 secciones: header, bio, platforms, KPIs, next post y generaciones
 * recientes.
 */
import { useNavigate, useParams } from 'react-router-dom';

import { Card, EmptyState, PageHeader, StatusBadge } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';
import { formatReach, formatEngagementRate } from '../casting/castingData.js';
import {
  formatScheduledCount,
  nextPostLabel,
  statusLabel,
  tagsFromVoice,
} from './personaStudioData.js';


export function PersonaStudio({ studio, loading = false, error = null }) {
  const navigate = useNavigate();
  const { tenantSlug, personaId } = useParams();
  const { can } = usePermissions();

  if (loading) {
    return (
      <Card padding="lg">
        <p role="status" aria-live="polite">Cargando estudio…</p>
      </Card>
    );
  }
  if (error || !studio?.persona) {
    return (
      <EmptyState
        title="Personaje no disponible"
        description="Es posible que haya sido archivado o que no tengas acceso."
      />
    );
  }

  const { persona, stats, next_post, platforms_connected, recent_generations } = studio;
  const tags = tagsFromVoice(persona.voice || {});
  const goEditFace = () => navigate(`/t/${tenantSlug}/influencer/personas/${personaId}/edit/face`);
  const goGenerate = () => navigate(`/t/${tenantSlug}/influencer/personas/${personaId}/generate`);
  const goFeed = () => navigate(`/t/${tenantSlug}/influencer/personas/${personaId}/feed`);

  return (
    <div data-module="influencer" data-view="studio">
      <PageHeader eyebrow="Ravit Studio" title={persona.name} description={persona.handle ? `@${persona.handle}` : ''} />

      {/* Header con CTAs */}
      <Card padding="md">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <div aria-hidden="true" style={{
            width: 72, height: 72, borderRadius: '50%',
            background: 'var(--color-surface-emphasis, #eee)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 700, fontSize: 28,
          }}>
            {persona.name?.[0]?.toUpperCase() ?? '?'}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 18 }}>{persona.name}</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>
              {formatScheduledCount(persona.status, stats?.scheduled_count)}
            </div>
          </div>
          <StatusBadge tone={persona.status === 'active' ? 'success' : 'neutral'}>
            {statusLabel(persona.status)}
          </StatusBadge>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-3)' }}>
          {can('influencer.personas.write') && (
            <button type="button" onClick={goEditFace}>Editar cara</button>
          )}
          {can('influencer.generate') && (
            <button type="button" onClick={goGenerate}>Generar contenido</button>
          )}
          <button type="button" onClick={goFeed}>Ver feed</button>
        </div>
      </Card>

      {/* Bio + tags */}
      {tags.length > 0 && (
        <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Identidad y voz</div>
          <ul aria-label="Tags de identidad" style={{
            display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)',
            margin: 0, padding: 0, listStyle: 'none',
          }}>
            {tags.map((t) => (
              <li key={t} style={{
                padding: '2px 8px',
                borderRadius: 999,
                background: 'var(--color-surface-emphasis, #f3f4f6)',
                fontSize: 12,
              }}>{t}</li>
            ))}
          </ul>
        </Card>
      )}

      {/* Platforms */}
      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Plataformas conectadas</div>
        {platforms_connected?.length ? (
          <ul aria-label="Conexiones" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {platforms_connected.map((c) => (
              <li key={c.platform} style={{ display: 'flex', gap: 'var(--space-2)', padding: '4px 0' }}>
                <span style={{ fontWeight: 600 }}>{c.platform}</span>
                <span style={{ color: 'var(--color-text-subtle, #6b7280)' }}>{c.external_handle || '—'}</span>
                <StatusBadge tone={c.status === 'connected' ? 'success' : 'warning'}>{c.status}</StatusBadge>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ margin: 0, color: 'var(--color-text-subtle, #6b7280)' }}>
            No hay plataformas conectadas todavía.
          </p>
        )}
      </Card>

      {/* KPIs */}
      <ul aria-label="Métricas del personaje" style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 'var(--space-3)', margin: 'var(--space-3) 0 0', padding: 0, listStyle: 'none',
      }}>
        <KpiTile label="Posts" value={stats?.posts_total ?? 0} />
        <KpiTile label="Alcance" value={formatReach(stats?.reach_30d ?? 0)} />
        <KpiTile label="Engagement" value={formatEngagementRate(stats?.engagement_rate ?? 0)} />
      </ul>

      {/* Next post */}
      {next_post && (
        <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
          <div style={{ fontWeight: 600 }}>Próximo post</div>
          <div style={{ color: 'var(--color-text-subtle, #6b7280)' }}>
            {nextPostLabel(next_post) ?? 'Sin programación'}
          </div>
        </Card>
      )}

      {/* Recent generations */}
      <Card padding="md" style={{ marginTop: 'var(--space-3)' }}>
        <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Generaciones recientes</div>
        {recent_generations?.length ? (
          <ul aria-label="Últimas generaciones" style={{
            display: 'flex', gap: 'var(--space-2)', overflowX: 'auto',
            margin: 0, padding: 0, listStyle: 'none',
          }}>
            {recent_generations.map((g) => (
              <li key={g.id} style={{
                minWidth: 160, padding: 'var(--space-2)',
                border: '1px solid var(--color-border-subtle, #e5e7eb)',
                borderRadius: 'var(--radius-md, 6px)',
              }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{g.kind}</div>
                <StatusBadge tone={g.status === 'succeeded' ? 'success' : 'neutral'}>{g.status}</StatusBadge>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ margin: 0, color: 'var(--color-text-subtle, #6b7280)' }}>
            Sin generaciones todavía.
          </p>
        )}
      </Card>
    </div>
  );
}


function KpiTile({ label, value }) {
  return (
    <li style={{
      background: 'var(--color-surface, #fff)',
      padding: 'var(--space-3)',
      borderRadius: 'var(--radius-md, 8px)',
      border: '1px solid var(--color-border-subtle, #e5e7eb)',
    }}>
      <div style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: 22 }}>{value}</div>
    </li>
  );
}
