import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { DigestSubscribersSummary } from './components/DigestSubscribersSummary.jsx';
import DigestSubscriptionsPanel from './components/DigestSubscriptionsPanel.jsx';
import { useDigestReportsData } from './hooks/useDigestReportsData.js';
import styles from './DigestReports.module.css';

/**
 * UI-008.4 — Reportes · Digest (Manager).
 *
 * Manager-facing view that lists the scheduled digests (daily / weekly) and
 * their subscribers, backed by the `digest/subscriptions` CRUD endpoints. The
 * subscribers-management UI is the relocated `DigestSubscriptionsPanel` (moved
 * verbatim from the tenant-setup feature — the wizard's `NotificationsTab`
 * still embeds it from its new location). A small `DigestSubscribersSummary`
 * adds a glance-level header (N destinos, X diarios / Y semanales). Gated by
 * `digest.write` RW; the backend remains the authority.
 *
 * Visual reference: `docs/HTML DESIGN/Manager/27 _ Reportes _ Digest.html`.
 * Declared intentional differences: the HTML's "Enviar ahora" action and the
 * rich KPI "Preview · digest diario" panel have no backing endpoints (the only
 * digest endpoints are the 4 subscription CRUD calls) — they are deferred, not
 * fabricated. No data is invented.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function DigestReports({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state } = useDigestReportsData({ session, tenantId: tenant?.id });

  return (
    <RequirePermission permissions={permissions} capability="digest.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Reportes"
          title={module?.label || 'Digest periódico'}
          description="Resumen automático de KPIs por email y WhatsApp. El digest diario sale a las 08:00 hora local del tenant; el semanal los lunes 08:00 con la semana cerrada Lun-Dom."
        />

        {state.error ? (
          <AlertBanner tone="danger" title={state.error} />
        ) : null}

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para gestionar las suscripciones al digest."
            />
          </Card>
        ) : (
          <>
            <DigestSubscribersSummary summary={state.summary} />
            <DigestSubscriptionsPanel session={session} tenantId={state.tenantId} />
          </>
        )}
      </section>
    </RequirePermission>
  );
}
