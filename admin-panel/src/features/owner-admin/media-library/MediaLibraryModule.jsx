import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { MediaGrid } from './components/MediaGrid.jsx';
import { MediaUploader } from './components/MediaUploader.jsx';
import { PromotionFormDrawer } from './components/PromotionFormDrawer.jsx';
import { PromotionsList } from './components/PromotionsList.jsx';
import { useMediaLibraryData } from './hooks/useMediaLibraryData.js';
import styles from './MediaLibraryModule.module.css';

/**
 * UI-007.11 — IA · Medios y promociones.
 *
 * Refactor of the legacy `MediaLibraryModule` (546 LOC) into a feature with an
 * orchestrator + `useMediaLibraryData` hook + pure `mediaLibraryData.js` + the
 * split components: `MediaGrid`, `MediaUploader`, `PromotionFormDrawer` and
 * `PromotionsList`. Media/promotion CRUD, file kind inference + size validation
 * are preserved verbatim. Gated by `media.write` (RW); the backend remains the
 * authority.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/19 _ IA · Medios y promociones.html`.
 * Declared difference: the HTML's "Resumen del bucket" KPIs (file count, total
 * size, 30d sends, most-used) and the per-asset "usos" counter are not modelled
 * by the media endpoints — they are deferred; no data is fabricated.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function MediaLibraryModule({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const { state, actions } = useMediaLibraryData({ session, tenant });

  return (
    <RequirePermission permissions={permissions} capability="media.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="IA & Canales"
          title={module?.label || 'Medios y promociones'}
          description="Fotos, videos y PDFs que el bot puede enviar durante el agendamiento. Las promociones se vinculan a servicios — el bot las ofrece automáticamente cuando aplican."
          actions={
            <div className={styles.headerActions}>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.openCreatePromo}
                disabled={!state.tenantId}
              >
                Nueva promoción
              </button>
              <button
                type="button"
                className={styles.primaryButton}
                onClick={actions.openUpload}
                disabled={!state.tenantId}
              >
                Subir medio
              </button>
            </div>
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
              description="Elige un tenant activo para gestionar su biblioteca de medios."
            />
          </Card>
        ) : (
          <div className={styles.layout}>
            <MediaGrid
              assets={state.assets}
              isLoading={state.isLoading}
              isBusy={state.isBusy}
              onEditTags={actions.editAssetTags}
              onDelete={actions.deleteAsset}
            />
            <PromotionsList
              promotions={state.promotions}
              assetsById={state.assetsById}
              servicesById={state.servicesById}
              isBusy={state.isBusy}
              onEdit={actions.openEditPromo}
              onRemove={actions.removePromo}
            />
          </div>
        )}

        <MediaUploader
          open={state.uploadOpen}
          uploadForm={state.uploadForm}
          isBusy={state.isBusy}
          onChange={actions.setUploadForm}
          onPickFile={actions.pickFile}
          onSubmit={actions.upload}
          onClose={actions.closeUpload}
        />
        <PromotionFormDrawer
          open={state.promoOpen}
          promoForm={state.promoForm}
          editingPromoId={state.editingPromoId}
          assets={state.assets}
          services={state.services}
          isBusy={state.isBusy}
          onChange={actions.setPromoForm}
          onSubmit={actions.submitPromo}
          onClose={actions.closePromo}
        />
      </section>
    </RequirePermission>
  );
}
