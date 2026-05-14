import { KpiTile } from '../../../../components/ui/index.js';
import { TYPE_LABEL } from '../meta.js';
import styles from '../FeatureFlags.module.css';

/**
 * Feature flags KPI grid. Mirrors the HTML reference
 * (`docs/HTML DESIGN/Platform Owner/08 _ Feature flags.html`): total flags,
 * how many default to `on`, and the breakdown by flag type.
 *
 * @param {{ summary: object }} props
 */
export function FeatureFlagKpis({ summary }) {
  const total = summary?.total ?? 0;
  const on = summary?.on ?? 0;
  const byType = summary?.by_type || {};
  const features = byType.feature ?? 0;
  const killSwitches = byType.kill ?? 0;

  return (
    <section className={styles.kpis} aria-label="Indicadores de feature flags">
      <KpiTile
        label="Flags en el catálogo"
        value={String(total)}
        footnote="capacidades del producto con flag"
      />
      <KpiTile
        label="Default en On"
        value={String(on)}
        footnote={`${summary?.off ?? 0} en Off`}
      />
      <KpiTile
        label={TYPE_LABEL.feature}
        value={String(features)}
        footnote="features GA con flag"
      />
      <KpiTile
        label={TYPE_LABEL.kill}
        value={String(killSwitches)}
        footnote="kill-switches de dependencias críticas"
      />
    </section>
  );
}
