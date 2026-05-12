import { useEffect, useRef, useState } from 'react';

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

function TenantSwitcher({ activeTenantId, canSwitchTenants, onTenantChange, tenantOptions }) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    function onDocClick(event) {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', onDocClick);
      return () => document.removeEventListener('mousedown', onDocClick);
    }
    return undefined;
  }, [open]);

  const activeTenant =
    tenantOptions.find((tenant) => tenant.id === activeTenantId) ?? tenantOptions[0];
  if (!activeTenant) return null;

  return (
    <div className="tenant-switcher" ref={wrapperRef}>
      <button
        type="button"
        className="tenant-switcher-trigger"
        onClick={() => canSwitchTenants && setOpen((value) => !value)}
        disabled={!canSwitchTenants}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={canSwitchTenants ? 'Cambiar de tenant' : 'Tenant único'}
      >
        <span className="tenant-switcher-avatar" aria-hidden="true">
          {tenantInitials(activeTenant)}
        </span>
        <span className="tenant-switcher-meta">
          <strong>{tenantTitle(activeTenant)}</strong>
          <small>{tenantSubtitle(activeTenant)}</small>
        </span>
        {canSwitchTenants ? (
          <span className="tenant-switcher-caret" aria-hidden="true">
            ▾
          </span>
        ) : null}
      </button>

      {open && canSwitchTenants ? (
        <ul className="tenant-switcher-menu" role="listbox">
          <li className="tenant-switcher-menu-header">Tus tenants</li>
          {tenantOptions.map((tenant) => {
            const isActive = tenant.id === activeTenant.id;
            return (
              <li key={tenant.id}>
                <button
                  type="button"
                  className={`tenant-switcher-option${isActive ? ' active' : ''}`}
                  onClick={() => {
                    onTenantChange(tenant.id);
                    setOpen(false);
                  }}
                  role="option"
                  aria-selected={isActive}
                >
                  <span className="tenant-switcher-avatar small" aria-hidden="true">
                    {tenantInitials(tenant)}
                  </span>
                  <span className="tenant-switcher-meta">
                    <strong>{tenantTitle(tenant)}</strong>
                    <small>{tenantSubtitle(tenant)}</small>
                  </span>
                  {isActive ? (
                    <span className="tenant-switcher-check" aria-hidden="true">
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

export function Sidebar({
  activeModuleId,
  activeTenantId,
  canSwitchTenants,
  modules,
  onModuleSelect,
  onTenantChange,
  tenantOptions,
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">IA</span>
        <div>
          <strong>CopilotoIA</strong>
          <small>Admin Panel</small>
        </div>
      </div>

      <TenantSwitcher
        activeTenantId={activeTenantId}
        canSwitchTenants={canSwitchTenants}
        onTenantChange={onTenantChange}
        tenantOptions={tenantOptions}
      />

      <nav aria-label="Módulos de administración">
        {modules.map((module) => (
          <button
            className={module.id === activeModuleId ? 'nav-item active' : 'nav-item'}
            key={module.id}
            onClick={() => onModuleSelect(module.id)}
            type="button"
          >
            {module.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
