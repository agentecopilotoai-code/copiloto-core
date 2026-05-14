import { useMemo, useState } from 'react';

import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { MEDIA_KIND_LABELS, formatBytes } from '../mediaLibraryData.js';
import styles from '../MediaLibraryModule.module.css';

/**
 * Media assets grid with a client-side label/tag search box. Presentational —
 * the asset list comes from the `useMediaLibraryData` hook; row actions are
 * passed in as callbacks.
 *
 * @param {{
 *   assets: Array<object>,
 *   isLoading: boolean,
 *   isBusy: boolean,
 *   onEditTags: (asset: object) => void,
 *   onDelete: (asset: object) => void,
 * }} props
 */
export function MediaGrid({ assets, isLoading, isBusy, onEditTags, onDelete }) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return assets;
    return assets.filter((asset) => {
      const haystack = [asset.label, asset.description, ...(asset.tags || [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [assets, query]);

  return (
    <Card padding="md">
      <CardHeader
        title={`Biblioteca (${assets.length})`}
        subtitle="Fotos, videos y PDFs que el bot puede enviar durante el agendamiento."
        actions={
          <input
            type="search"
            className={styles.search}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar por etiqueta o nombre"
            aria-label="Buscar medios"
          />
        }
      />

      {isLoading ? (
        <p className={styles.hint}>Cargando…</p>
      ) : filtered.length === 0 ? (
        <EmptyState
          title={assets.length === 0 ? 'Sin archivos' : 'Sin resultados'}
          description={
            assets.length === 0
              ? 'Aún no hay archivos. Sube el primero con «Subir medio».'
              : 'Ningún archivo coincide con la búsqueda.'
          }
        />
      ) : (
        <div className={styles.mediaGrid}>
          {filtered.map((asset) => (
            <article key={asset.id} className={styles.mediaCard}>
              <div className={styles.mediaCardHead}>
                <strong>{asset.label}</strong>
                <StatusBadge tone="neutral">
                  {MEDIA_KIND_LABELS[asset.kind] || asset.kind}
                </StatusBadge>
              </div>
              <p className={styles.mediaMeta}>{formatBytes(asset.size_bytes)}</p>
              {(asset.tags || []).length ? (
                <div className={styles.tagRow}>
                  {asset.tags.map((tag) => (
                    <StatusBadge key={tag} tone="accent">
                      {tag}
                    </StatusBadge>
                  ))}
                </div>
              ) : null}
              {asset.description ? (
                <p className={styles.mediaDesc}>{asset.description}</p>
              ) : null}
              <div className={styles.cardActions}>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={isBusy}
                  onClick={() => onEditTags(asset)}
                >
                  Tags
                </button>
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={isBusy}
                  onClick={() => onDelete(asset)}
                >
                  Eliminar
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </Card>
  );
}
