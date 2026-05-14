import styles from '../shell.module.css';

/**
 * Topbar compartido por los shells: breadcrumb (eyebrow + título del módulo
 * activo) y un slot de acciones a la derecha (banner read-only, CTAs, etc.).
 *
 * @param {{
 *   eyebrow: string,
 *   title: string,
 *   actions?: import('react').ReactNode,
 * }} props
 */
export function ShellTopbar({ eyebrow, title, actions = null }) {
  return (
    <header className={styles.topbar}>
      <div className={styles.topbarTitle}>
        <p>{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      {actions ? <div className={styles.topbarActions}>{actions}</div> : null}
    </header>
  );
}
