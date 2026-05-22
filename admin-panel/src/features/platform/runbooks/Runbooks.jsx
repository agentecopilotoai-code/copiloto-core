import { useMemo, useState } from 'react';

import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { RunbookFilters } from './components/RunbookFilters.jsx';
import { RunbookList } from './components/RunbookList.jsx';
import { RunbookViewer } from './components/RunbookViewer.jsx';
import { useRunbookDetail } from './hooks/useRunbookDetail.js';
import { useRunbooks } from './hooks/useRunbooks.js';
import styles from './Runbooks.module.css';

/**
 * UI-006.6 — Runbooks.
 *
 * Platform-owner catalogue of the operational runbooks under `docs/runbooks/`,
 * with client-side search + category filtering and an in-place viewer. Reads
 * `GET /v1/platform/runbooks` and `GET /v1/platform/runbooks/{slug}` (both
 * router-protected by `require_platform_owner` + `require_mfa_for_privileged`).
 *
 * The runbook bodies are rendered server-side through
 * `render_markdown_to_safe_html` (TASK-0076) — the same fully-escaped Markdown
 * subset used for public legal pages.
 *
 * Visual reference: the "Runbooks disponibles" panel of
 * `docs/HTML DESIGN/Platform Owner/04 _ Incidentes.html`.
 */
export function Runbooks() {
  const { session, profile } = useTenantContext();
  const permissions = usePermissions();
  const { runbooks, categories, loading, error, refresh } = useRunbooks({ session });

  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [selectedSlug, setSelectedSlug] = useState(null);

  const detail = useRunbookDetail({ session, slug: selectedSlug });

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return runbooks.filter((runbook) => {
      if (category && runbook.category !== category) return false;
      if (!needle) return true;
      return (
        runbook.title.toLowerCase().includes(needle) ||
        runbook.slug.toLowerCase().includes(needle)
      );
    });
  }, [runbooks, search, category]);

  return (
    <RequirePermission permissions={permissions} capability="platform.runbooks.read" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Audit global"
          title="Runbooks"
          description="Catálogo de runbooks operacionales de docs/runbooks/. Cada alerta de Prometheus apunta a uno de estos documentos; aquí se buscan, filtran y leen renderizados a HTML seguro."
          actions={
            <button type="button" className={styles.refreshButton} onClick={refresh}>
              Actualizar
            </button>
          }
        />

        {error ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar el catálogo de runbooks"
              description={error}
              action={
                <button type="button" className={styles.refreshButton} onClick={refresh}>
                  Reintentar
                </button>
              }
            />
          </Card>
        ) : (
          <Card padding="md">
            <RunbookFilters
              search={search}
              category={category}
              categories={categories}
              onSearchChange={setSearch}
              onCategoryChange={setCategory}
            />
            {loading && runbooks.length === 0 ? (
              <EmptyState
                title="Cargando runbooks…"
                description="Leyendo el catálogo de docs/runbooks/."
              />
            ) : (
              <RunbookList runbooks={filtered} onSelect={setSelectedSlug} />
            )}
          </Card>
        )}

        <RunbookViewer
          open={selectedSlug !== null}
          runbook={detail.runbook}
          loading={detail.loading}
          error={detail.error}
          onClose={() => setSelectedSlug(null)}
        />
      </section>
    </RequirePermission>
  );
}
