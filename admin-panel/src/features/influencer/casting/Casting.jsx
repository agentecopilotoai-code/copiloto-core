/**
 * UI-INFLU-004 — Casting Home con personajes (orquestador).
 *
 * Estilos via `_shared/RavitStyles.module.css` + `Casting.module.css`
 * local. Sistema visual fiel a la paleta Ravit Studio confirmada
 * (docs/influencer/04 _ Paleta.html).
 */
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { PersonaCard } from '../../../components/domain/PersonaCard.jsx';
import { usePermissions } from '../../../permissions/index.js';
import shared from '../_shared/RavitStyles.module.css';
import {
  CATEGORY_FILTER_OPTIONS,
  SORT_OPTIONS,
  filterByCategory,
  formatEngagementRate,
  formatReach,
  sortPersonas,
} from './castingData.js';
import { CastingEmptyState } from './CastingEmptyState.jsx';
import styles from './Casting.module.css';


function CastingKpis({ kpis }) {
  if (!kpis) return null;
  const tiles = [
    { label: 'Personajes activos', value: kpis.active_personas ?? 0 },
    { label: 'Posts este mes', value: kpis.posts_this_month ?? 0 },
    { label: 'Alcance total', value: formatReach(kpis.total_reach) },
    { label: 'Engagement medio', value: formatEngagementRate(kpis.avg_engagement) },
  ];
  return (
    <ul aria-label="KPIs del casting" className={styles.kpiGrid}>
      {tiles.map((t) => (
        <li key={t.label} className={shared.kpiTile}>
          <div className={shared.kpiNumber}>{t.value}</div>
          <div className={shared.kpiLabel}>{t.label}</div>
        </li>
      ))}
    </ul>
  );
}


function CastingFilters({ category, sort, onCategoryChange, onSortChange }) {
  return (
    <div role="toolbar" aria-label="Filtros del casting" className={styles.filters}>
      <div role="group" aria-label="Categoría" className={styles.chipsRow}>
        {CATEGORY_FILTER_OPTIONS.map((opt) => {
          const isActive = (category ?? null) === opt.value;
          return (
            <button
              key={opt.label}
              type="button"
              onClick={() => onCategoryChange(opt.value)}
              aria-pressed={isActive}
              className={isActive ? styles.chipActive : styles.chipIdle}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <label className={styles.sortLabel}>
        <span>Ordenar por</span>
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value)}
          aria-label="Ordenar personajes"
          className={styles.sortSelect}
        >
          {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
    </div>
  );
}


function PersonaGrid({ personas, onOpenStudio, onCreate }) {
  if (personas.length === 0) {
    return (
      <p role="status" className={shared.textSubtle}>
        No hay personajes para los filtros seleccionados.
      </p>
    );
  }
  return (
    <ul aria-label="Lista de personajes" className={styles.personaGrid}>
      {personas.map((p) => (
        <li key={p.id}>
          <PersonaCard persona={p} onOpenStudio={onOpenStudio} />
        </li>
      ))}
      {/* UI-INFLU-014.8: card "Crear nuevo personaje" al final del grid */}
      <li>
        <CreateNewPersonaCard onClick={onCreate} />
      </li>
    </ul>
  );
}


function CreateNewPersonaCard({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: '100%', minHeight: 300,
        background: '#eaf7ef', border: '2px dashed #2DBB6A',
        borderRadius: 14, cursor: 'pointer',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 12,
        padding: 24,
      }}
    >
      <div style={{
        width: 56, height: 56, borderRadius: '50%',
        background: '#2DBB6A', color: '#fff',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 28, fontWeight: 700,
      }}>+</div>
      <div style={{ fontWeight: 700, fontSize: 16, color: '#0a0f1f' }}>
        Crear nuevo personaje
      </div>
      <p style={{
        margin: 0, fontSize: 13, textAlign: 'center',
        color: 'var(--ravit-text-muted, #6b7280)',
        maxWidth: 220,
      }}>
        Sube una cara, define identidad y plataformas. Listo para postear en 5 minutos.
      </p>
      <div style={{
        marginTop: 4, padding: '8px 16px', borderRadius: 8,
        background: '#2DBB6A', color: '#fff', fontWeight: 600, fontSize: 13,
        display: 'inline-flex', alignItems: 'center', gap: 6,
      }}>
        <span aria-hidden="true">✦</span> Empezar
      </div>
    </button>
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
    return <CastingEmptyState />;
  }

  if (personas.length === 0) {
    return <CastingEmptyState />;
  }

  const openStudio = (persona) => {
    // UI-INFLU-014.11: cada personaje tiene su propio URL con su ID.
    // - Drafts → /personas/{id}/wizard/step-1 (continúa configurándolo).
    // - Activos/pausados → /personas/{id}/studio.
    if (persona.status === 'draft') {
      navigate(`/t/${tenantSlug}/influencer/personas/${persona.id}/wizard/step-1`);
      return;
    }
    navigate(`/t/${tenantSlug}/influencer/personas/${persona.id}/studio`);
  };

  return (
    <div className={shared.page} data-module="influencer" data-view="casting">
      <div className={shared.pageHeader}>
        <div className={shared.eyebrow}>Ravit Studio · Casting</div>
        <h1 className={shared.h1Page}>Tu casting</h1>
        <p className={shared.textSubtle}>
          Los personajes que generan contenido en nombre de tu marca.
        </p>
      </div>

      <div className={styles.sections}>
        <CastingKpis kpis={casting?.kpis} />
        <CastingFilters
          category={category}
          sort={sort}
          onCategoryChange={setCategory}
          onSortChange={setSort}
        />
        <PersonaGrid
          personas={filtered}
          onOpenStudio={openStudio}
          onCreate={() => navigate(`/t/${tenantSlug}/influencer/personas/new`)}
        />
      </div>
    </div>
  );
}
