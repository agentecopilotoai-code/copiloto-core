/**
 * Panel "Miembros del tenant" — vive dentro del FleetDrawer.
 *
 * Lista usuarios del tenant + sus roles del chrome. Permite:
 *   - Agregar miembro (invitar por email, asignar rol).
 *   - Cambiar rol de un miembro existente.
 *   - Revocar membresía.
 *
 * Llama `/v1/tenants/{tenantId}/members` (require platform_owner + MFA).
 */
import { useCallback, useEffect, useState } from 'react';

import { Button, Card, EmptyState } from '../../../../components/ui/index.js';
import {
  listTenantMembers, inviteTenantMember,
  updateTenantMemberRole, removeTenantMember,
} from '../../../../services/coreApi.js';
import styles from '../FleetTenants.module.css';

const ROLE_OPTIONS = [
  { value: 'owner',   label: 'Owner — acceso total al tenant' },
  { value: 'admin',   label: 'Admin — configuración + operación' },
  { value: 'manager', label: 'Manager — análisis y campañas' },
  { value: 'agent',   label: 'Agent — operación diaria' },
  { value: 'viewer',  label: 'Viewer — solo lectura' },
];

export function TenantMembersPanel({ session, tenant }) {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(false);
  const [newMember, setNewMember] = useState({ email: '', role: 'admin' });

  const load = useCallback(async () => {
    if (!session || !tenant?.id) return;
    setLoading(true); setError(null);
    try {
      const r = await listTenantMembers(session, tenant.id);
      setMembers(r.items || []);
    } catch (err) {
      setError(err?.message || 'No se pudieron cargar los miembros.');
    } finally {
      setLoading(false);
    }
  }, [session, tenant?.id]);

  useEffect(() => { load(); }, [load]);

  async function handleAdd(event) {
    event.preventDefault();
    if (!newMember.email.trim()) return;
    setAdding(true); setError(null);
    try {
      await inviteTenantMember(session, tenant.id, {
        email: newMember.email.trim().toLowerCase(),
        role: newMember.role,
      });
      setNewMember({ email: '', role: 'admin' });
      await load();
    } catch (err) {
      setError(err?.message || 'No se pudo agregar el miembro.');
    } finally {
      setAdding(false);
    }
  }

  async function handleRoleChange(userId, newRole) {
    setError(null);
    try {
      await updateTenantMemberRole(session, tenant.id, userId, newRole);
      await load();
    } catch (err) {
      setError(err?.message || 'No se pudo cambiar el rol.');
    }
  }

  async function handleRemove(userId, email) {
    if (!window.confirm(`¿Revocar membresía de ${email}?`)) return;
    setError(null);
    try {
      await removeTenantMember(session, tenant.id, userId);
      await load();
    } catch (err) {
      setError(err?.message || 'No se pudo revocar la membresía.');
    }
  }

  return (
    <section className={styles.membersPanel}>
      <h3 className={styles.membersHeading}>Miembros del tenant</h3>
      <p className={styles.helpText}>
        Usuarios con acceso a <strong>{tenant?.display_name || tenant?.slug}</strong>.
        El rol controla qué módulos y acciones puede ver/ejecutar.
      </p>

      <Card padding="md" className={styles.addMemberCard}>
        <form onSubmit={handleAdd} className={styles.addMemberForm}>
          <label className={styles.formField}>
            <span>Email del nuevo miembro</span>
            <input
              type="email" required
              value={newMember.email}
              onChange={(e) => setNewMember({ ...newMember, email: e.target.value })}
              placeholder="usuario@empresa.com"
              data-testid="add-member-email"
            />
          </label>
          <label className={styles.formField}>
            <span>Rol</span>
            <select
              value={newMember.role}
              onChange={(e) => setNewMember({ ...newMember, role: e.target.value })}
              data-testid="add-member-role"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </label>
          <Button
            type="submit" variant="primary"
            disabled={adding || !newMember.email.trim()}
            data-testid="add-member-submit"
          >
            {adding ? 'Agregando…' : '+ Agregar miembro'}
          </Button>
        </form>
      </Card>

      {error ? (
        <div role="alert" className={styles.formError}>{error}</div>
      ) : null}

      {loading ? (
        <p className={styles.helpText}>Cargando miembros…</p>
      ) : members.length === 0 ? (
        <EmptyState
          title="Sin miembros"
          description="El tenant no tiene usuarios asignados. Agregá el primer miembro con el formulario de arriba."
        />
      ) : (
        <table className={styles.membersTable} data-testid="members-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Nombre</th>
              <th>Rol</th>
              <th>MFA</th>
              <th>Último login</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => {
              const role = (m.roles && m.roles[0]) || m.role || 'viewer';
              return (
                <tr key={m.user_id} data-testid={`member-row-${m.email}`}>
                  <td>{m.email}</td>
                  <td>{m.display_name || '—'}</td>
                  <td>
                    <select
                      value={role}
                      onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                      data-testid={`member-role-${m.email}`}
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>{r.value}</option>
                      ))}
                    </select>
                  </td>
                  <td>{m.mfa_enabled ? '✓' : '—'}</td>
                  <td>{m.last_login_at ? new Date(m.last_login_at).toLocaleDateString() : '—'}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.linkButtonDanger}
                      onClick={() => handleRemove(m.user_id, m.email)}
                      data-testid={`member-remove-${m.email}`}
                    >
                      Revocar
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
