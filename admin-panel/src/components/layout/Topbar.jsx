import { adminPath } from '../../services/adminSession.js';

export function Topbar({ activeModule, profile }) {
  const displayName = profile.name || profile.email || profile.sub;
  const roles = profile.roles?.length ? profile.roles.join(', ') : 'sin roles';
  const supportMode = profile.support_mode ? ' · support mode' : '';

  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Tenant operations</p>
        <h1>{activeModule.label}</h1>
      </div>
      <div className="profile">
        {profile.picture ? <img alt="" src={profile.picture} /> : null}
        <div>
          <strong>{displayName}</strong>
          <small>
            {roles}
            {supportMode}
          </small>
        </div>
        <form method="post" action={adminPath('/admin/logout')}>
          <button type="submit">Salir</button>
        </form>
      </div>
    </header>
  );
}
