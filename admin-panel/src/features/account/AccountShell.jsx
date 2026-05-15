import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import { adminPath } from '../../services/adminSession.js';
import styles from './AccountShell.module.css';

const SECTIONS = [
  { to: 'profile', label: 'Perfil' },
  { to: 'preferences', label: 'Apariencia' },
  { to: 'notifications', label: 'Notificaciones' },
  { to: 'sessions', label: 'Sesiones' },
];

/**
 * UI-016.7 — layout transversal de "Mi cuenta".
 *
 * Vive fuera del shell tenant-scoped: `/account/*` no requiere tenant activo,
 * solo sesión. La nav lateral lista 4 sub-rutas; el botón "Volver al panel"
 * lleva al `IndexRedirect` (`/`), que reenruta al usuario a su home según rol.
 *
 * Tokens 100% desde `var(--...)`; no se usan colores hardcoded.
 */
export function AccountShell() {
  const navigate = useNavigate();

  return (
    <div className={styles.shell}>
      <header className={styles.shellHeader}>
        <div className={styles.shellHeaderInner}>
          <a className={styles.brand} href="/admin/" aria-label="Inicio CopilotoIA">
            <span className={styles.brandMark} aria-hidden="true">
              IA
            </span>
            <span className={styles.brandText}>
              <strong>CopilotoIA</strong>
              <small>· Cuenta del usuario</small>
            </span>
          </a>
          <button
            type="button"
            className={styles.shellBackBtn}
            onClick={() => navigate('/')}
          >
            ← Volver al panel
          </button>
        </div>
      </header>

      <div className={styles.shellLayout}>
        <aside aria-label="Secciones de la cuenta">
          <nav className={styles.sideNav}>
            <p className={styles.sideNavTitle}>Mi cuenta</p>
            {SECTIONS.map((section) => (
              <NavLink
                key={section.to}
                to={section.to}
                className={({ isActive }) =>
                  isActive
                    ? `${styles.sideNavItem} ${styles.sideNavItemActive}`
                    : styles.sideNavItem
                }
              >
                {section.label}
              </NavLink>
            ))}

            <div className={styles.sideNavLogout}>
              <form
                className={styles.logoutForm}
                method="post"
                action={adminPath('/admin/logout')}
              >
                <button type="submit" className={styles.logoutButton}>
                  Cerrar sesión
                </button>
              </form>
            </div>
          </nav>
        </aside>

        <main className={styles.content} id="account-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
