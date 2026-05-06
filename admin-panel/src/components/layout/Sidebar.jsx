export function Sidebar({ activeModuleId, activeTenantId, modules, onModuleSelect, onTenantChange, tenantOptions }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">IA</span>
        <div>
          <strong>CopilotoIA</strong>
          <small>Admin Panel</small>
        </div>
      </div>

      <label className="tenant-picker">
        Tenant activo
        <select value={activeTenantId} onChange={(event) => onTenantChange(event.target.value)}>
          {tenantOptions.map((tenant) => (
            <option key={tenant.id} value={tenant.id}>
              {tenant.label}
            </option>
          ))}
        </select>
      </label>

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
