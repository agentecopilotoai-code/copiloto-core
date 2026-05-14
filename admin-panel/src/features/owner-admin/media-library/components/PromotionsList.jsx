import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { MEDIA_KIND_LABELS } from '../mediaLibraryData.js';
import styles from '../MediaLibraryModule.module.css';

/**
 * Promotions list. Presentational — the promotions + the asset/service lookup
 * maps come from the `useMediaLibraryData` hook; row actions are callbacks.
 *
 * @param {{
 *   promotions: Array<object>,
 *   assetsById: Map<string, object>,
 *   servicesById: Map<string, object>,
 *   isBusy: boolean,
 *   onEdit: (promo: object) => void,
 *   onRemove: (promo: object) => void,
 * }} props
 */
export function PromotionsList({ promotions, assetsById, servicesById, isBusy, onEdit, onRemove }) {
  return (
    <Card padding="md">
      <CardHeader
        title={`Promociones (${promotions.length})`}
        subtitle="El bot las ofrece automáticamente durante el booking cuando aplican."
      />

      {promotions.length === 0 ? (
        <EmptyState
          title="Sin promociones"
          description="Aún no hay promociones configuradas. Crea la primera con «Nueva promoción»."
        />
      ) : (
        <ul className={styles.promoList}>
          {promotions.map((promo) => {
            const media = promo.media_asset_id ? assetsById.get(promo.media_asset_id) : null;
            const serviceNames = (promo.applies_to_service_ids || [])
              .map((id) => servicesById.get(id)?.name || id.slice(0, 8))
              .join(', ');
            return (
              <li key={promo.id} className={styles.promoItem}>
                <div className={styles.promoMain}>
                  <div className={styles.promoTitleRow}>
                    <strong>{promo.name}</strong>
                    <StatusBadge tone={promo.is_active ? 'success' : 'neutral'}>
                      {promo.is_active ? 'Activa' : 'Pausada'}
                    </StatusBadge>
                    {promo.discount_percent != null ? (
                      <span className={styles.promoDiscount}>{promo.discount_percent}% off</span>
                    ) : null}
                  </div>
                  <p className={styles.promoMeta}>
                    {media
                      ? `Con ${MEDIA_KIND_LABELS[media.kind]}: ${media.label}`
                      : 'Solo texto'}
                  </p>
                  <p className={styles.promoMeta}>
                    {serviceNames ? `Servicios: ${serviceNames}` : 'Todos los servicios'}
                  </p>
                </div>
                <div className={styles.rowActions}>
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    disabled={isBusy}
                    onClick={() => onEdit(promo)}
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    className={styles.dangerButton}
                    disabled={isBusy}
                    onClick={() => onRemove(promo)}
                  >
                    Eliminar
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
