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


function PersonaGrid({ personas, onOpenStudio }) {
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
    return <CastingEmptyState />;
  }

  if (personas.length === 0) {
    return <CastingEmptyState />;
  }

  const openStudio = (persona) => {
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
        <PersonaGrid personas={filtered} onOpenStudio={openStudio} />
      </div>
    </div>
  );
}
