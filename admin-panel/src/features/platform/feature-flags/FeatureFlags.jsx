import { useMemo, useState } from 'react';

import { Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { FeatureFlagFilters } from './components/FeatureFlagFilters.jsx';
import { FeatureFlagKpis } from './components/FeatureFlagKpis.jsx';
import { FeatureFlagsTable } from './components/FeatureFlagsTable.jsx';
import { useFeatureFlags } from './hooks/useFeatureFlags.js';
import styles from './FeatureFlags.module.css';

/**
 * UI-006.8 — Feature flags.
 *
 * Platform-owner read-only catalogue of the product's feature flags. Reads
 * `GET /v1/platform/feature-flags` (router-protected by `require_platform_owner`
 * + `require_mfa_for_privileged`), which serves a static registry — no DB.
 *
 * Visual reference: `docs/HTML DESIGN/Platform Owner/08 _ Feature flags.html`.
 * Intentional difference: the HTML shows live toggles, gradual rollout sliders
 * and per-tenant overrides. Those need a persisted, audited, writable
 * feature-flag system that does not exist — the UI backlog flags UI-006.8 as
 * "confirmar con el equipo antes de cablear" precisely for that reason. This
 * view ships the honest read-only catalogue; the writable system is a separate
 * backend ticket.
 */
export function FeatureFlags() {
  const { session, profile } = useTenantContext();
  const permissions = usePermissions();
  const { flags, flagTypes, summary, note, loading, error, refresh } = useFeatureFlags({
    session,
  });

  const [search, setSearch] = useState('');
  const [type, setType] = useState('');

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return flags.filter((flag) => {
      if (type && flag.type !== type) return false;
      if (!needle) return true;
      return (
        flag.key.toLowerCase().includes(needle) ||
        (flag.description || '').toLowerCase().includes(needle)
      );
    });
  }, [flags, search, type]);

  return (
    <RequirePermission
      permissions={permissions}
      capability="platform.feature_flags.read"
      mode="R"
    >
      <section className={styles.page}>
        <PageHeader
          eyebrow="Plataforma · Acceso"
          title="Feature flags"
          description="Catálogo de los feature flags del producto, cada uno mapeado a la TASK que lo introdujo. Vista de solo lectura; el toggle en vivo, el rollout gradual y los overrides por tenant requieren un sistema de feature flags persistido y auditado (ticket de backend aparte)."
          actions={
            <button type="button" className={styles.refreshButton} onClick={refresh}>
              Actualizar
            </button>
          }
        />

        {error ? (
          <Card padding="md">
            <EmptyState
              title="No se pudo cargar el catálogo de feature flags"
              description={error}
              action={
                <button type="button" className={styles.refreshButton} onClick={refresh}>
                  Reintentar
                </button>
              }
            />
          </Card>
        ) : (
          <>
            <FeatureFlagKpis summary={summary || {}} />
            <Card padding="md">
              <FeatureFlagFilters
                search={search}
                type={type}
                types={flagTypes}
                onSearchChange={setSearch}
                onTypeChange={setType}
              />
              <FeatureFlagsTable flags={filtered} loading={loading} />
            </Card>
            {note ? <p className={styles.note}>{note}</p> : null}
          </>
        )}
      </section>
    </RequirePermission>
  );
}
