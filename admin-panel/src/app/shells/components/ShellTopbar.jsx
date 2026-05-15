import { ThemeToggle } from './ThemeToggle.jsx';
import { TenantBrandLogo } from './TenantBrandLogo.jsx';
import styles from '../shell.module.css';

/**
 * Topbar compartido por los shells: breadcrumb (eyebrow + título del módulo
 * activo), un slot de logo opcional del tenant (UI-012) a la izquierda, y un
 * slot de acciones a la derecha (banner read-only, CTAs, etc.). El
 * `ThemeToggle` (UI-012) se monta siempre al final del slot de acciones, en
 * los 3 shells, sin requerir wiring extra.
 *
 * @param {{
 *   eyebrow: string,
 *   title: string,
 *   actions?: import('react').ReactNode,
 *   tenant?: { brand_logo_url?: string, display_name?: string, slug?: string, name?: string },
 * }} props
 */
export function ShellTopbar({ eyebrow, title, actions = null, tenant = null }) {
  const hasBrand = Boolean(tenant);

  return (
    <header className={styles.topbar}>
      <div className={styles.topbarLeft}>
        {hasBrand ? <TenantBrandLogo tenant={tenant} /> : null}
        <div className={styles.topbarTitle}>
          <p>{eyebrow}</p>
          <h1>{title}</h1>
        </div>
      </div>
      <div className={styles.topbarActions}>
        {actions}
        <ThemeToggle />
      </div>
    </header>
  );
}
