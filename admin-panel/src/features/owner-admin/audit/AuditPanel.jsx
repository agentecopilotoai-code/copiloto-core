import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { AuditFilters } from './components/AuditFilters.jsx';
import { AuditTable } from './components/AuditTable.jsx';
import { PrivacyTools } from './components/PrivacyTools.jsx';
import { useAuditData } from './hooks/useAuditData.js';
import styles from './AuditPanel.module.css';

/**
 * UI-007.15 — Config · Auditoría.
 *
 * Redesign of the legacy `AuditPanel` (255 LOC) into a feature with an
 * orchestrator + `useAuditData` hook + pure `auditData.js` + the split
 * components: `AuditFilters` (dense filter form + CSV export), `AuditTable`
 * (DataTable of audit logs) and `PrivacyTools` (GDPR contact suppression +
 * tenant data export + DPA policy summary). Log querying, CSV/tenant export
 * and contact suppression are preserved verbatim. Gated by `audit.read`; the
 * backend remains the authority.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/23 _ Config · Auditoría.html`.
 * Declared difference: the HTML's category-count sidebar and the per-row
 * "Cambio" / "IP/SDK" columns are not exposed by `listAuditLogsFiltered` — they
 * are deferred; the table shows the real endpoint fields. No data is fabricated.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function AuditPanel({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, actions } = useAuditData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="audit.read">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Configuración"
          title={module?.label || 'Auditoría'}
          description="Trazabilidad inmutable de cada acción administrativa, edición de configuración o decisión del bot que afecta datos del cliente. Append-only · retención larga para cumplimiento."
        />

        {state.notice ? (
          <AlertBanner
            tone={
              state.notice.type === 'error'
                ? 'danger'
                : state.notice.type === 'info'
                  ? 'info'
                  : 'success'
            }
            title={state.notice.text}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissNotice}
              >
                Cerrar
              </button>
            }
          />
        ) : null}

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para consultar su registro de auditoría."
            />
          </Card>
        ) : (
          <>
            <AuditFilters
              filters={state.filters}
              isBusy={state.isBusy}
              tenantId={state.tenantId}
              onChange={actions.setFilters}
              onQuery={actions.loadLogs}
              onExportCsv={actions.exportCsv}
            />
            <AuditTable logs={state.logs} loaded={state.loaded} />
            <PrivacyTools
              suppressId={state.suppressId}
              isBusy={state.isBusy}
              tenantId={state.tenantId}
              onSuppressIdChange={actions.setSuppressId}
              onSuppress={actions.suppressContact}
              onExportTenantData={actions.exportTenantData}
            />
          </>
        )}
      </section>
    </RequirePermission>
  );
}
