import styles from '../Landing.module.css';

/**
 * UI-016.4 — Header sticky con logo, nav (Producto · Canales · Precios ·
 * Clientes · Recursos) y CTAs (Iniciar sesión + Contactar ventas + Solicitar
 * demo).
 *
 * "Iniciar sesión" apunta a `loginHref` (por defecto `/admin/login`, que
 * dispara el redirect a Auth0 vía el flujo existente del SPA). "Contactar
 * ventas" y "Solicitar demo" usan `mailto:`.
 *
 * @param {Object} props
 * @param {string} props.loginHref
 * @param {string} props.demoMailto
 * @param {string} props.salesMailto
 */
export function LandingHeader({ loginHref, demoMailto, salesMailto }) {
  const navItems = [
    { id: 'producto', label: 'Producto' },
    { id: 'canales', label: 'Canales' },
    { id: 'precios', label: 'Precios' },
    { id: 'clientes', label: 'Clientes' },
    { id: 'recursos', label: 'Recursos' },
  ];

  return (
    <header className={styles.header}>
      <div className={`${styles.container} ${styles.headerInner}`}>
        <a href="/" className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            C
          </span>
          <span>
            <span className={styles.brandName}>CopilotoIA</span>
            <br />
            <span className={styles.brandTagline}>Agendamiento por IA</span>
          </span>
        </a>

        <nav className={styles.nav} aria-label="Navegación principal">
          {navItems.map((item) => (
            <a key={item.id} href={`#${item.id}`} className={styles.navLink}>
              {item.label}
            </a>
          ))}
        </nav>

        <div className={styles.actions}>
          <a href={loginHref} className={`${styles.btnLink} ${styles.btnLinkGhost}`}>
            Iniciar sesión
          </a>
          <a href={salesMailto} className={styles.btnLink}>
            Contactar ventas
          </a>
          <a href={demoMailto} className={`${styles.btnLink} ${styles.btnLinkPrimary}`}>
            Solicitar demo →
          </a>
        </div>
      </div>
    </header>
  );
}
