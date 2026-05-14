import { useEffect, useRef, useState } from 'react';

import styles from '../shell.module.css';

function tenantInitials(tenant) {
  const source = tenant?.slug || tenant?.display_name || tenant?.label || 't';
  return source.replace(/[^a-zA-Z0-9]/g, '').slice(0, 2).toUpperCase() || 'T';
}

function tenantTitle(tenant) {
  return tenant?.display_name || tenant?.slug || tenant?.label || 'Tenant';
}

function tenantSubtitle(tenant) {
  if (tenant?.role) return tenant.role;
  if (tenant?.roles?.length) return tenant.roles[0];
  return tenant?.id ? tenant.id.slice(0, 8) : '';
}

/**
 * Selector de tenant estilo Slack. Solo abre el menú cuando el usuario
 * pertenece a más de un tenant (`canSwitchTenants`).
 *
 * @param {{
 *   activeTenantId?: string,
 *   canSwitchTenants?: boolean,
 *   onTenantChange: (tenantId: string) => void,
 *   tenantOptions: Array<object>,
 * }} props
 */
export function TenantSwitcher({
  activeTenantId,
  canSwitchTenants,
  onTenantChange,
  tenantOptions,
}) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onDocClick(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const activeTenant =
    tenantOptions.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions[0];
  if (!activeTenant) return null;

  return (
    <div className={styles.tenantSwitcher} ref={wrapperRef}>
      <button
        type="button"
        className={styles.tenantSwitcherTrigger}
        onClick={() => canSwitchTenants && setOpen((value) => !value)}
        disabled={!canSwitchTenants}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={canSwitchTenants ? 'Cambiar de tenant' : 'Tenant único'}
      >
        <span className={styles.tenantAvatar} aria-hidden="true">
          {tenantInitials(activeTenant)}
        </span>
        <span className={styles.tenantMeta}>
          <strong>{tenantTitle(activeTenant)}</strong>
          <small>{tenantSubtitle(activeTenant)}</small>
        </span>
        {canSwitchTenants ? (
          <span className={styles.tenantCaret} aria-hidden="true">
            ▾
          </span>
        ) : null}
      </button>

      {open && canSwitchTenants ? (
        <ul className={styles.tenantMenu} role="listbox">
          <li className={styles.tenantMenuHeader}>Tus tenants</li>
          {tenantOptions.map((tenant) => {
            const isActive = tenant.id === activeTenant.id;
            return (
              <li key={tenant.id}>
                <button
                  type="button"
                  className={
                    isActive
                      ? `${styles.tenantOption} ${styles.tenantOptionActive}`
                      : styles.tenantOption
                  }
                  onClick={() => {
                    onTenantChange(tenant.id);
                    setOpen(false);
                  }}
                  role="option"
                  aria-selected={isActive}
                >
                  <span
                    className={`${styles.tenantAvatar} ${styles.tenantAvatarSmall}`}
                    aria-hidden="true"
                  >
                    {tenantInitials(tenant)}
                  </span>
                  <span className={styles.tenantMeta}>
                    <strong>{tenantTitle(tenant)}</strong>
                    <small>{tenantSubtitle(tenant)}</small>
                  </span>
                  {isActive ? (
                    <span className={styles.tenantCheck} aria-hidden="true">
                      ✓
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
