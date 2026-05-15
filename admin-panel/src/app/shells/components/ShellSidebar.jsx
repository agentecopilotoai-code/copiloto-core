import { Link } from 'react-router-dom';

import { adminPath } from '../../../services/adminSession.js';
import styles from '../shell.module.css';

function userInitials(profile) {
  const source = profile?.name || profile?.email || profile?.sub || 'U';
  const parts = source.trim().split(/\s+/);
  const initials = parts.length > 1 ? parts[0][0] + parts[1][0] : source.slice(0, 2);
  return initials.toUpperCase();
}

/**
 * Tarjeta de usuario del sidebar. El avatar + nombre son un `<Link>` a
 * `/account/profile` (UI-016.7) — el HTML T3 deja claro que "estas pantallas
 * viven detrás del avatar del sidebar". El botón "Salir" sigue siendo el
 * submit del form POST a `/admin/logout` que Auth0 espera.
 */
function UserCard({ profile }) {
  const displayName = profile?.name || profile?.email || profile?.sub || 'Usuario';
  const role = profile?.roles?.length ? profile.roles[0] : 'sin rol';
  return (
    <div className={styles.userCard}>
      <Link
        to="/account/profile"
        className={styles.userTrigger}
        aria-label={`Abrir mi cuenta (${displayName})`}
      >
        <span className={styles.userAvatar} aria-hidden="true">
          {profile?.picture ? <img alt="" src={profile.picture} /> : userInitials(profile)}
        </span>
        <span className={styles.userMeta}>
          <strong>{displayName}</strong>
          <small>{role}</small>
        </span>
      </Link>
      <form className={styles.logoutForm} method="post" action={adminPath('/admin/logout')}>
        <button className={styles.logoutButton} type="submit">
          Salir
        </button>
      </form>
    </div>
  );
}

/**
 * Sidebar compartido por los 3 shells: marca + slots opcionales (tenant switcher,
 * badge) + navegación agrupada + tarjeta de usuario con logout.
 *
 * @param {{
 *   navGroups: Array<{section: string, items: Array<{id, label, disabled}>}>,
 *   activeModuleId?: string,
 *   onModuleSelect: (moduleId: string) => void,
 *   profile?: object,
 *   tenantSwitcher?: import('react').ReactNode,
 *   badge?: import('react').ReactNode,
 * }} props
 */
export function ShellSidebar({
  navGroups,
  activeModuleId,
  onModuleSelect,
  profile,
  tenantSwitcher = null,
  badge = null,
}) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <span className={styles.brandMark} aria-hidden="true">
          IA
        </span>
        <div className={styles.brandText}>
          <strong>CopilotoIA</strong>
          <small>Admin Panel</small>
        </div>
      </div>

      {tenantSwitcher}
      {badge}

      <nav className={styles.nav} aria-label="Módulos de administración">
        {navGroups.map((group) => (
          <div key={group.section}>
            <p className={styles.navSectionTitle}>{group.section}</p>
            {group.items.map((item) => {
              if (item.disabled) {
                return (
                  <span
                    key={item.id}
                    className={`${styles.navItem} ${styles.navItemDisabled}`}
                    aria-disabled="true"
                  >
                    {item.label}
                  </span>
                );
              }
              return (
                <button
                  key={item.id}
                  type="button"
                  className={
                    item.id === activeModuleId
                      ? `${styles.navItem} ${styles.navItemActive}`
                      : styles.navItem
                  }
                  aria-current={item.id === activeModuleId ? 'page' : undefined}
                  onClick={() => onModuleSelect(item.id)}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <UserCard profile={profile} />
    </aside>
  );
}
