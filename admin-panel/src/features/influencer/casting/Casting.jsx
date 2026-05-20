/**
 * UI-INFLU-004 — Casting Home con personajes (orquestador).
 *
 * Consume `GET /v1/influencer/casting` (TASK-INFLU-017) y monta:
 *  - `CastingKpis`: 4 tiles globales.
 *  - `CastingFilters`: chips de categoría + sort selector.
 *  - `PersonaGrid`: lista de `PersonaCard`.
 *
 * Si `personas=[]`, delega al `CastingEmptyState` (UI-INFLU-003).
 */
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { PageHeader } from '../../../components/ui/index.js';
import { PersonaCard } from '../../../components/domain/PersonaCard.jsx';
import { usePermissions } from '../../../permissions/index.js';
import {
  CATEGORY_FILTER_OPTIONS,
  SORT_OPTIONS,
  filterByCategory,
  formatEngagementRate,
  formatReach,
  sortPersonas,
} from './castingData.js';
import { CastingEmptyState } from './CastingEmptyState.jsx';


function CastingKpis({ kpis }) {
  if (!kpis) return null;
  const tiles = [
    { label: 'Personajes activos', value: kpis.active_personas ?? 0 },
    { label: 'Posts este mes', value: kpis.posts_this_month ?? 0 },
    { label: 'Alcance total', value: formatReach(kpis.total_reach) },
    { label: 'Engagement medio', value: formatEngagementRate(kpis.avg_engagement) },
  ];
  return (
    <ul
      aria-label="KPIs del casting"
      style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 'var(--space-3)', margin: 0, padding: 0, listStyle: 'none',
      }}
    >
      {tiles.map((t) => (
        <li key={t.label} style={{
          background: 'var(--color-surface, #fff)',
          padding: 'var(--space-3)',
          borderRadius: 'var(--radius-md, 8px)',
          border: '1px solid var(--color-border-subtle, #e5e7eb)',
        }}>
          <div style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>{t.label}</div>
          <div style={{ fontWeight: 700, fontSize: 22 }}>{t.value}</div>
        </li>
      ))}
    </ul>
  );
}


function CastingFilters({ category, sort, onCategoryChange, onSortChange }) {
  return (
    <div role="toolbar" aria-label="Filtros del casting"
      style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--space-2)' }}>
      <div role="group" aria-label="Categoría"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)' }}>
        {CATEGORY_FILTER_OPTIONS.map((opt) => {
          const isActive = (category ?? null) === opt.value;
          return (
            <button
              key={opt.label}
              type="button"
              onClick={() => onCategoryChange(opt.value)}
              aria-pressed={isActive}
              style={{
                padding: '4px 10px',
                borderRadius: 999,
                border: '1px solid var(--color-border, #d1d5db)',
                background: isActive ? 'var(--color-action-primary-bg, #111)' : 'transparent',
                color: isActive ? 'var(--color-action-primary-fg, #fff)' : 'inherit',
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <label
        style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)', marginLeft: 'auto' }}>
        <span style={{ fontSize: 13, color: 'var(--color-text-subtle, #6b7280)' }}>Ordenar por</span>
        <select value={sort} onChange={(e) => onSortChange(e.target.value)} aria-label="Ordenar personajes">
          {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
    </div>
  );
}


function PersonaGrid({ personas, onOpenStudio }) {
  if (personas.length === 0) {
    return (
      <p role="status" style={{ color: 'var(--color-text-subtle, #6b7280)' }}>
        No hay personajes para los filtros seleccionados.
      </p>
    );
  }
  return (
    <ul
      aria-label="Lista de personajes"
      style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: 'var(--space-3)', margin: 0, padding: 0, listStyle: 'none',
      }}
    >
      {personas.map((p) => (
        <li key={p.id}>
          <PersonaCard persona={p} onOpenStudio={onOpenStudio} />
        </li>
      ))}
    </ul>
  );
}


export function Casting({ casting }) {
  const navigate = useNavigate();
  const { tenantSlug } = useParams();
  const { can } = usePermissions();
  const [category, setCategory] = useState(null);
  const [sort, setSort] = useState('activity');

  const personas = casting?.personas ?? [];
  const filtered = useMemo(
    () => sortPersonas(filterByCategory(personas, category), sort),
    [personas, category, sort],
  );

  if (!can('influencer.personas.read')) {
    return <CastingEmptyState />;  // fallback con CTA disabled (mismo gate)
  }

  if (personas.length === 0) {
    return <CastingEmptyState />;
  }

  const openStudio = (persona) => {
    navigate(`/t/${tenantSlug}/influencer/personas/${persona.id}/studio`);
  };

  return (
    <div data-module="influencer" data-view="casting">
      <PageHeader
        eyebrow="Ravit Studio"
        title="Tu casting"
        description="Los personajes que generan contenido en nombre de tu marca."
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <CastingKpis kpis={casting?.kpis} />
        <CastingFilters
          category={category}
          sort={sort}
          onCategoryChange={setCategory}
          onSortChange={setSort}
        />
        <PersonaGrid personas={filtered} onOpenStudio={openStudio} />
      </div>
    </div>
  );
}
