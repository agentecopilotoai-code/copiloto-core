import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { DlqDetailModal } from './components/DlqDetailModal.jsx';
import { DlqErrorChips } from './components/DlqErrorChips.jsx';
import { DlqTable } from './components/DlqTable.jsx';
import { useOutboundDlqData } from './hooks/useOutboundDlqData.js';
import styles from './OutboundDLQ.module.css';

/**
 * UI-009.4 — Operación · Outbound DLQ.
 *
 * Redesign of the legacy `OutboundDLQ` (198 LOC) into a feature with an
 * orchestrator + `useOutboundDlqData` hook + pure `outboundDlqData.js` + the
 * `DlqErrorChips` (filter) / `DlqTable` / `DlqDetailModal` split. The list
 * fetch, the error-code filter and the retry handler (with its native confirm
 * + audited `outbound.dlq.retried` server action) are preserved verbatim.
 * Gated by `outbound_dlq.retry` (RW); the backend remains the authority.
 *
 * Visual reference: `docs/HTML DESIGN/Agente/31 _ Operación · Outbound DLQ.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function OutboundDLQ({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, actions } = useOutboundDlqData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="outbound_dlq.retry" mode="RW">
      <section className={styles.page} data-module="outbound-dlq">
        <PageHeader
          eyebrow="Operación"
          title={module?.label || 'Outbound DLQ'}
          description="Mensajes que el event_worker no pudo entregar a Meta. Filtra por código de error, revisa el detalle y reintenta el envío cuando la causa esté resuelta (token rotado, ventana 24 h, rate limit, etc.)."
          actions={
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={actions.refresh}
              disabled={state.isLoading || !state.tenantId}
            >
              {state.isLoading ? 'Cargando…' : 'Refrescar'}
            </button>
          }
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
              description="Elige un tenant activo para revisar su cola de mensajes fallidos."
            />
          </Card>
        ) : (
          <>
            <DlqErrorChips
              totals={state.totals}
              activeFilter={state.errorCodeFilter}
              onToggle={actions.toggleFilter}
            />
            <DlqTable
              items={state.items}
              totals={state.totals}
              isLoading={state.isLoading}
              retryingId={state.retryingId}
              onViewDetail={actions.openDetail}
              onRetry={actions.retry}
            />
          </>
        )}

        <DlqDetailModal item={state.selected} onClose={actions.closeDetail} />
      </section>
    </RequirePermission>
  );
}
