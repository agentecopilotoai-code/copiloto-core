import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  inviteTenantMember,
  listTenantMembers,
  removeTenantMember,
  updateTenantMemberRole,
} from '../../../services/coreApi.js';

const ROLE_OPTIONS = [
  { value: 'owner', label: 'Owner', description: 'Acceso total. Solo otros owners pueden asignar este rol.' },
  { value: 'admin', label: 'Admin', description: 'Configura el tenant, equipo y módulos.' },
  { value: 'manager', label: 'Manager', description: 'Operación diaria y analítica.' },
  { value: 'agent', label: 'Agent', description: 'Atiende conversaciones e inbox.' },
  { value: 'viewer', label: 'Viewer', description: 'Solo lectura.' },
];

const ROLE_COLORS = {
  owner: '#7c3aed',
  admin: '#0ea5e9',
  manager: '#16a34a',
  agent: '#f59e0b',
  viewer: '#64748b',
};

function highestRole(roles) {
  const order = ['owner', 'admin', 'manager', 'agent', 'viewer'];
  for (const role of order) {
    if (roles?.includes(role)) return role;
  }
  return roles?.[0] || 'viewer';
}

function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
}

function RoleBadge({ role }) {
  return (
    <span
      className="role-chip"
      style={{
        background: `${ROLE_COLORS[role] || '#475569'}22`,
        color: ROLE_COLORS[role] || '#475569',
        border: `1px solid ${ROLE_COLORS[role] || '#475569'}55`,
        padding: '2px 8px',
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: 0.4,
      }}
    >
      {role}
    </span>
  );
}

function Notice({ notice }) {
  if (!notice) return null;
  return <p className={`notice ${notice.type}`}>{notice.text}</p>;
}

export function TeamModule({ module, session, tenant }) {
  const [members, setMembers] = useState([]);
  const [auth0Enabled, setAuth0Enabled] = useState(false);
  const [notice, setNotice] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', display_name: '', role: 'agent' });

  const profileRoles = useMemo(() => {
    const fromProfile = session?.profile?.roles || [];
    const fromTenant = tenant?.roles || [];
    return new Set([...fromProfile, ...fromTenant]);
  }, [session?.profile?.roles, tenant?.roles]);
  const callerIsOwner = profileRoles.has('owner') || profileRoles.has('platform_owner');

  const refresh = useCallback(async () => {
    if (!tenant?.id) return;
    setIsLoading(true);
    setNotice(null);
    try {
      const result = await listTenantMembers(session, tenant.id);
      setMembers(result?.members || []);
      setAuth0Enabled(Boolean(result?.auth0_management_enabled));
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'No se pudo cargar el equipo del tenant.' });
    } finally {
      setIsLoading(false);
    }
  }, [session, tenant?.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleInvite(event) {
    event.preventDefault();
    if (!tenant?.id) return;
    if (!inviteForm.email.trim()) {
      setNotice({ type: 'error', text: 'Ingresa el email del nuevo miembro.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const result = await inviteTenantMember(session, tenant.id, {
        email: inviteForm.email.trim(),
        display_name: inviteForm.display_name.trim() || undefined,
        role: inviteForm.role,
      });
      setInviteForm({ email: '', display_name: '', role: 'agent' });
      // TASK-0085 / BUG06: the API no longer returns a password-change
      // ticket URL — Auth0 emails the invitation directly to the new user.
      // The UI must NOT display, copy or persist any such link.
      if (result?.auth0?.invited) {
        setNotice({
          type: 'success',
          text: 'Invitación enviada. El usuario recibirá un email de Auth0 para configurar su contraseña.',
        });
      } else if (result?.auth0_skipped) {
        setNotice({
          type: 'success',
          text: 'Miembro agregado. Auth0 Management API no está habilitado: sincroniza manualmente desde el dashboard.',
        });
      } else {
        setNotice({ type: 'success', text: 'Miembro agregado.' });
      }
      await refresh();
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'No se pudo invitar al miembro.' });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRoleChange(member, nextRole) {
    if (!tenant?.id) return;
    if (nextRole === 'owner' && !callerIsOwner) {
      setNotice({ type: 'error', text: 'Solo un owner puede asignar el rol owner.' });
      return;
    }
    const confirmed = window.confirm(
      `¿Cambiar el rol de ${member.email} de "${highestRole(member.roles)}" a "${nextRole}"?`,
    );
    if (!confirmed) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await updateTenantMemberRole(session, tenant.id, member.user_id, nextRole);
      setNotice({ type: 'success', text: 'Rol actualizado. El próximo JWT del usuario reflejará el cambio.' });
      await refresh();
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'No se pudo actualizar el rol.' });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRemove(member) {
    if (!tenant?.id) return;
    const confirmed = window.confirm(
      `¿Revocar el acceso de ${member.email} a este tenant? Esta acción no se puede deshacer.`,
    );
    if (!confirmed) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await removeTenantMember(session, tenant.id, member.user_id);
      setNotice({ type: 'success', text: 'Acceso revocado.' });
      await refresh();
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'No se pudo revocar el acceso.' });
    } finally {
      setIsBusy(false);
    }
  }

  const ownerCount = members.filter((m) => m.roles?.includes('owner')).length;

  return (
    <section className="module-card team-module">
      <header className="module-header">
        <p className="eyebrow">{module?.label || 'Equipo'}</p>
        <h2>Miembros del tenant</h2>
        <p className="hint">
          Invita, asigna roles y revoca acceso. El rol <strong>owner</strong> tiene acceso total; el resto
          se rige por la jerarquía admin → manager → agent → viewer.
        </p>
      </header>

      {!auth0Enabled ? (
        <div className="warn-banner" role="status">
          Auth0 Management API no está habilitada. Los cambios se reflejarán en el próximo login del usuario;
          sincroniza manualmente desde el dashboard de Auth0 si es necesario.
        </div>
      ) : null}

      <Notice notice={notice} />

      <form className="form-grid" onSubmit={handleInvite}>
        <h3>Invitar miembro</h3>
        <div className="form-row">
          <label>
            Email
            <input
              type="email"
              required
              value={inviteForm.email}
              onChange={(event) => setInviteForm((f) => ({ ...f, email: event.target.value }))}
              placeholder="usuario@dominio.com"
            />
          </label>
          <label>
            Nombre (opcional)
            <input
              type="text"
              value={inviteForm.display_name}
              onChange={(event) => setInviteForm((f) => ({ ...f, display_name: event.target.value }))}
              placeholder="María Pérez"
            />
          </label>
          <label>
            Rol
            <select
              value={inviteForm.role}
              onChange={(event) => setInviteForm((f) => ({ ...f, role: event.target.value }))}
            >
              {ROLE_OPTIONS.map((option) => {
                const disabled = option.value === 'owner' && !callerIsOwner;
                return (
                  <option key={option.value} value={option.value} disabled={disabled}>
                    {option.label}
                    {disabled ? ' (solo owners)' : ''}
                  </option>
                );
              })}
            </select>
          </label>
        </div>
        <button className="primary-action" type="submit" disabled={isBusy || !tenant?.id}>
          {isBusy ? 'Enviando…' : 'Invitar'}
        </button>
      </form>

      <div className="table-wrapper">
        {isLoading ? <p className="hint">Cargando equipo…</p> : null}
        <table className="data-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Email</th>
              <th>Rol</th>
              <th>Último login</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {members.length === 0 && !isLoading ? (
              <tr>
                <td colSpan={5} className="hint">
                  Aún no hay miembros para este tenant.
                </td>
              </tr>
            ) : null}
            {members.map((member) => {
              const role = highestRole(member.roles);
              const isOnlyOwner = role === 'owner' && ownerCount <= 1;
              const blockOwnerEdit = role === 'owner' && !callerIsOwner;
              return (
                <tr key={member.user_id}>
                  <td>
                    <strong>{member.display_name || '—'}</strong>
                    {member.status === 'invited' ? (
                      <span className="hint"> (pendiente)</span>
                    ) : null}
                  </td>
                  <td>{member.email}</td>
                  <td>
                    <RoleBadge role={role} />{' '}
                    <select
                      value={role}
                      disabled={isBusy || blockOwnerEdit}
                      onChange={(event) => handleRoleChange(member, event.target.value)}
                    >
                      {ROLE_OPTIONS.map((option) => {
                        const disabled =
                          option.value === 'owner' && !callerIsOwner && role !== 'owner';
                        return (
                          <option key={option.value} value={option.value} disabled={disabled}>
                            {option.label}
                          </option>
                        );
                      })}
                    </select>
                  </td>
                  <td>{formatDate(member.last_login_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="danger-action"
                      disabled={isBusy || isOnlyOwner || blockOwnerEdit}
                      title={
                        isOnlyOwner
                          ? 'No se puede revocar al último owner del tenant.'
                          : blockOwnerEdit
                            ? 'Solo otro owner puede revocar a un owner.'
                            : 'Revocar acceso'
                      }
                      onClick={() => handleRemove(member)}
                    >
                      Revocar
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
