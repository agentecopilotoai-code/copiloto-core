import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { MarkdownEditor } from './components/MarkdownEditor.jsx';
import { PublishedDocuments } from './components/PublishedDocuments.jsx';
import { VersionHistory } from './components/VersionHistory.jsx';
import { useLegalData } from './hooks/useLegalData.js';
import styles from './LegalModule.module.css';

/**
 * UI-007.14 — Config · Legal.
 *
 * Redesign of the legacy `LegalModule` (356 LOC) into a feature with an
 * orchestrator + `useLegalData` hook + pure `legalData.js` + the split
 * components: `PublishedDocuments` (currently-published version per kind +
 * public URL), `MarkdownEditor` (side-by-side editor + sanitised preview) and
 * `VersionHistory` (append-only version tables with the publish action).
 * Draft creation, publishing and the safe Markdown-subset renderer are
 * preserved verbatim. Gated by `legal.write` (RW); the backend remains the
 * authority.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/22 _ Config · Legal.html`.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function LegalModule({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, publicUrl, actions } = useLegalData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="legal.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Configuración"
          title={module?.label || 'Legal'}
          description="Términos, Política de Privacidad y Aviso de Tratamiento de Datos. Todo es append-only y versionado — publicar archiva la versión anterior automáticamente (Circular SIC 002)."
        />

        {state.error ? (
          <AlertBanner
            tone="danger"
            title={state.error}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissError}
              >
                Cerrar
              </button>
            }
          />
        ) : null}
        {state.info ? (
          <AlertBanner
            tone="success"
            title={state.info}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissInfo}
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
              description="Elige un tenant activo para gestionar sus páginas legales."
            />
          </Card>
        ) : (
          <>
            <PublishedDocuments published={state.published} publicUrl={publicUrl} />
            <MarkdownEditor
              form={state.form}
              saving={state.saving}
              tenantId={state.tenantId}
              onFieldChange={actions.setFormField}
              onSubmit={actions.saveDraft}
            />
            <VersionHistory
              grouped={state.grouped}
              loading={state.loading}
              saving={state.saving}
              onPublish={actions.publish}
            />
          </>
        )}
      </section>
    </RequirePermission>
  );
}
