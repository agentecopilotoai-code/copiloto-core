import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { MyHandoffsList } from './components/MyHandoffsList.jsx';
import { useMyHandoffsData } from './hooks/useMyHandoffsData.js';
import { toHandoffRow } from './myHandoffsData.js';
import styles from './MyHandoffs.module.css';

/**
 * UI-009.2 — Operación · Mis handoffs (Agente).
 *
 * Vista del rol Agente que reutiliza la maquinaria del Inbox (`useInboxData` +
 * el componente de dominio `ConversationListItem`) con un filtro de handoffs
 * pre-aplicado. NO re-consulta nada: corre sobre la misma respuesta
 * tenant-scoped de `listConversations` que ya posee el Inbox y filtra en
 * cliente por `active_handoff_assigned_to = current_user`. Las acciones de
 * handoff (`acceptHandoff` / `releaseHandoff`) se reusan verbatim del Inbox.
 *
 * Gateada por `conversations.view` (modo R) vía `<RequirePermission>` — la
 * misma capability que el Inbox; el backend sigue siendo la autoridad.
 *
 * Referencia visual: `docs/HTML DESIGN/Agente/29 _ Operación _ Mis handoffs.html`.
 * Diferencias intencionales declaradas: el HTML muestra KPIs ("Resueltas hoy",
 * "% por bot", "tiempo medio", "cerca de SLA") y columnas de SLA por fila que
 * `listConversations` no expone — se difieren (no se inventan datos). Las tabs
 * `Colegas` / `Cerrados` tampoco tienen respaldo en el endpoint y se difieren.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function MyHandoffs({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useMyHandoffsData({ session, tenant, profile });

  const selectedRow = state.selectedConversation
    ? toHandoffRow(state.selectedConversation, state.currentUserId)
    : null;

  return (
    <RequirePermission permissions={permissions} capability="conversations.view" mode="R">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Operación"
          title={module?.label || 'Mis handoffs'}
          description="Conversaciones donde el bot escaló a humano. Tomarlas detiene la cascada automática y la conversación pasa a tu inbox personal hasta que la resuelvas."
          actions={
            <button
              type="button"
              className={styles.refreshButton}
              disabled={state.isBusy}
              onClick={() => actions.refreshConversations(true)}
            >
              Refrescar cola
            </button>
          }
        />

        {state.notice ? (
          <AlertBanner
            tone={state.notice.type === 'error' ? 'danger' : 'success'}
            title={state.notice.text}
            action={
              <button
                type="button"
                className={styles.refreshButton}
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
              description="Elige un tenant activo para ver tu cola de handoffs."
            />
          </Card>
        ) : (
          <div className={styles.layout}>
            <MyHandoffsList
              handoffs={state.handoffs}
              counts={state.counts}
              handoffFilter={state.handoffFilter}
              currentUserId={state.currentUserId}
              selectedConversationId={state.selectedConversationId}
              isBusy={state.isBusy}
              onFilterChange={actions.setHandoffFilter}
              onSelectConversation={actions.setSelectedConversationId}
              onTakeHandoff={actions.setSelectedConversationId}
            />

            <Card padding="md" className={styles.detail}>
              {selectedRow ? (
                <div className={styles.detailBody}>
                  <div>
                    <p className={styles.detailEyebrow}>Handoff seleccionado</p>
                    <h3 className={styles.detailTitle}>{selectedRow.contactLabel}</h3>
                    <p className={styles.detailMeta}>
                      {selectedRow.statusText} · esperando desde {selectedRow.waitingSince}
                    </p>
                    <p className={styles.detailMeta}>Asignación: {selectedRow.ownership}</p>
                  </div>
                  <div className={styles.detailActions}>
                    {selectedRow.isUnassigned ? (
                      <button
                        type="button"
                        className={styles.primaryButton}
                        disabled={state.isBusy}
                        onClick={actions.acceptHandoff}
                      >
                        Tomar handoff
                      </button>
                    ) : null}
                    {selectedRow.isMine ? (
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        disabled={state.isBusy}
                        onClick={actions.releaseHandoff}
                      >
                        Liberar al bot
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : (
                <EmptyState
                  title="Selecciona un handoff"
                  description="Elige una conversación de la cola para tomarla o liberarla."
                />
              )}
            </Card>
          </div>
        )}
      </section>
    </RequirePermission>
  );
}
