import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { SegmentsList } from './components/SegmentsList.jsx';
import { SegmentFormDrawer } from './components/SegmentFormDrawer.jsx';
import { SegmentPreviewPanel } from './components/SegmentPreviewPanel.jsx';
import { useSegmentsData } from './hooks/useSegmentsData.js';
import styles from './SegmentsModule.module.css';

/**
 * UI-008.3 — Segmentos (Manager).
 *
 * Refactor of the legacy `SegmentsModule` (489 LOC) into a feature with an
 * orchestrator + `useSegmentsData` hook + pure `segmentsData.js` + the split
 * components: `SegmentsList` (DataTable of segments with per-row actions —
 * edit / preview / refresh / delete), `SegmentRuleBuilder` (the dynamic rule
 * builder, composed inside `SegmentFormDrawer`'s create/edit `Modal`) and
 * `SegmentPreviewPanel` (the segment summary + live `previewContactSegment`
 * sample). Segment CRUD, preview and refresh — including the native delete
 * confirm — are preserved verbatim. Gated by `segments.write` (RW); the
 * backend remains the authority.
 *
 * Visual reference: `docs/HTML DESIGN/Manager/26 _ Segmentos.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function SegmentsModule({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useSegmentsData({ session, tenant });

  const ruleActions = {
    onJoinerChange: (joiner) => actions.setForm((prev) => ({ ...prev, joiner })),
    onAddRule: actions.addRule,
    onRemoveRule: actions.removeRule,
    onFieldChange: actions.changeRuleField,
    onOpChange: actions.changeRuleOp,
    onValueChange: actions.changeRuleValue,
    onListValueBlur: actions.blurRuleListValue,
  };

  return (
    <RequirePermission permissions={permissions} capability="segments.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Retención y reactivación"
          title={module?.label || 'Segmentos'}
          description={
            module?.summary ||
            'Los segmentos reutilizan reglas (ej. «Sin visita en 60+ días») como destinatarios de campañas y filtros de contactos. Los dinámicos se recalculan automáticamente.'
          }
          actions={
            <button
              type="button"
              className={styles.primaryButton}
              onClick={actions.startCreate}
              disabled={!state.tenantId || state.isBusy}
            >
              Nuevo segmento
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
              description="Elige un tenant activo para gestionar segmentos."
            />
          </Card>
        ) : (
          <div className={styles.layout}>
            <SegmentsList
              segments={state.segments}
              selectedId={state.selectedId}
              isBusy={state.isBusy}
              onSelect={actions.select}
              onEdit={actions.startEdit}
              onPreview={actions.preview}
              onRefresh={actions.refresh}
              onDelete={actions.remove}
            />
            <SegmentPreviewPanel segment={state.selectedSegment} preview={state.preview} />
          </div>
        )}

        <SegmentFormDrawer
          open={state.showForm}
          formMode={state.formMode}
          form={state.form}
          isBusy={state.isBusy}
          onChange={actions.setForm}
          onSubmit={actions.submit}
          onClose={actions.closeForm}
          ruleActions={ruleActions}
        />
      </section>
    </RequirePermission>
  );
}
