/**
 * PersonaCard — tarjeta de personaje del módulo Influencer (UI-INFLU-004).
 *
 * Se reusa en UI-INFLU-014 (filtro del calendario) por eso vive en
 * `components/domain/`. Mantiene la card ≤ 200 LOC.
 */
import { Card, StatusBadge } from '../ui/index.js';
import { formatEngagementRate, formatReach, categoryLabel } from
  '../../features/influencer/casting/castingData.js';


function statusTone(status) {
  switch (status) {
    case 'active': return 'success';
    case 'paused': return 'warning';
    case 'draft': return 'neutral';
    case 'archived': return 'neutral';
    default: return 'neutral';
  }
}


function statusLabel(status) {
  switch (status) {
    case 'active': return 'Activo';
    case 'paused': return 'Pausado';
    case 'draft': return 'Borrador';
    case 'archived': return 'Archivado';
    default: return status || 'Sin estado';
  }
}


export function PersonaCard({ persona, onOpenStudio }) {
  const handle = persona.handle ? `@${persona.handle}` : '';
  const ariaLabel = `Abrir estudio de ${persona.name}`;
  return (
    <Card padding="md" interactive>
      <div
        role="article"
        aria-label={`Personaje ${persona.name}`}
        style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
        data-persona-id={persona.id}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <div
            aria-hidden="true"
            style={{
              width: 48, height: 48, borderRadius: '50%',
              background: 'var(--color-surface-emphasis, #eee)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 600, fontSize: 18,
            }}
          >
            {persona.name?.[0]?.toUpperCase() ?? '?'}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600 }}>{persona.name}</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-subtle, #6b7280)' }}>{handle}</div>
          </div>
          <StatusBadge tone={statusTone(persona.status)}>{statusLabel(persona.status)}</StatusBadge>
        </div>

        <div style={{ fontSize: 13, color: 'var(--color-text-subtle, #6b7280)' }}>
          {categoryLabel(persona.category)}
        </div>

        <dl
          aria-label="Métricas del personaje"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 'var(--space-2)',
            margin: 0,
          }}
        >
          <PersonaStat label="Posts" value={persona.posts_total ?? 0} />
          <PersonaStat label="Alcance" value={formatReach(persona.reach_30d)} />
          <PersonaStat label="Engagement" value={formatEngagementRate(persona.engagement_rate)} />
        </dl>

        <button
          type="button"
          onClick={() => onOpenStudio?.(persona)}
          aria-label={ariaLabel}
          style={{
            marginTop: 'var(--space-2)',
            padding: 'var(--space-2) var(--space-3)',
            background: 'var(--color-action-primary-bg, #111)',
            color: 'var(--color-action-primary-fg, #fff)',
            border: 'none',
            borderRadius: 'var(--radius-md, 6px)',
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          Abrir estudio
        </button>
      </div>
    </Card>
  );
}


function PersonaStat({ label, value }) {
  return (
    <div>
      <dt style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)' }}>{label}</dt>
      <dd style={{ margin: 0, fontWeight: 600 }}>{value}</dd>
    </div>
  );
}
