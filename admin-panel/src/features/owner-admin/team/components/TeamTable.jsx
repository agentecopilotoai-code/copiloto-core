import { useMemo, useState } from 'react';

import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { ROLE_OPTIONS, ROLE_TONE, formatDate, highestRole, memberInitials } from '../teamData.js';
import styles from '../TeamModule.module.css';

/**
 * Team members table with a client-side name/email search box. Reuses
 * `DataTable`; presentational — the member list comes from the `useTeamData`
 * hook, row actions are callbacks. The owner-role guards (last owner cannot be
 * removed, only an owner can edit an owner) are preserved verbatim.
 *
 * @param {{
 *   members: Array<object>,
 *   isLoading: boolean,
 *   isBusy: boolean,
 *   isOwner: boolean,
 *   onChangeRole: (member: object, role: string) => void,
 *   onRemove: (member: object) => void,
 * }} props
 */
export function TeamTable({ members, isLoading, isBusy, isOwner, onChangeRole, onRemove }) {
  const [query, setQuery] = useState('');

  const ownerCount = useMemo(
    () => members.filter((m) => m.roles?.includes('owner')).length,
    [members],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return members;
    return members.filter((member) =>
      [member.display_name, member.email]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(needle),
    );
  }, [members, query]);

  const columns = [
    {
      key: 'member',
      header: 'Miembro',
      accessor: (row) => (
        <div className={styles.memberCell}>
          <span className={styles.avatar} aria-hidden="true">
            {memberInitials(row)}
          </span>
          <div className={styles.memberText}>
            <strong>
              {row.display_name || '—'}
              {row.status === 'invited' ? (
                <span className={styles.pending}> (pendiente)</span>
              ) : null}
            </strong>
            <span className={styles.memberEmail}>{row.email}</span>
          </div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Rol',
      accessor: (row) => {
        const role = highestRole(row.roles);
        const blockOwnerEdit = role === 'owner' && !isOwner;
        return (
          <div className={styles.roleCell}>
            <StatusBadge tone={ROLE_TONE[role] || 'neutral'}>{role}</StatusBadge>
            <select
              aria-label={`Cambiar rol de ${row.email}`}
              className={styles.roleSelect}
              value={role}
              disabled={isBusy || blockOwnerEdit}
              onChange={(event) => onChangeRole(row, event.target.value)}
            >
              {ROLE_OPTIONS.map((option) => {
                const disabled = option.value === 'owner' && !isOwner && role !== 'owner';
                return (
                  <option key={option.value} value={option.value} disabled={disabled}>
                    {option.label}
                  </option>
                );
              })}
            </select>
          </div>
        );
      },
    },
    { key: 'last_login', header: 'Último acceso', accessor: (row) => formatDate(row.last_login_at) },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => (
        <StatusBadge tone={row.status === 'invited' ? 'warning' : 'success'}>
          {row.status === 'invited' ? 'Pendiente' : 'Activo'}
        </StatusBadge>
      ),
    },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) => {
        const role = highestRole(row.roles);
        const isOnlyOwner = role === 'owner' && ownerCount <= 1;
        const blockOwnerEdit = role === 'owner' && !isOwner;
        return (
          <button
            type="button"
            className={styles.dangerButton}
            disabled={isBusy || isOnlyOwner || blockOwnerEdit}
            title={
              isOnlyOwner
                ? 'No se puede revocar al último owner del tenant.'
                : blockOwnerEdit
                  ? 'Solo otro owner puede revocar a un owner.'
                  : 'Revocar acceso'
            }
            onClick={() => onRemove(row)}
          >
            Revocar
          </button>
        );
      },
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title={`Miembros (${members.length})`}
        actions={
          <input
            type="search"
            className={styles.search}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar por nombre o email"
            aria-label="Buscar miembros"
          />
        }
      />
      {isLoading ? (
        <p className={styles.hint}>Cargando equipo…</p>
      ) : filtered.length === 0 ? (
        <EmptyState
          title={members.length === 0 ? 'Sin miembros' : 'Sin resultados'}
          description={
            members.length === 0
              ? 'Aún no hay miembros para este tenant. Invita al primero con «Invitar miembro».'
              : 'Ningún miembro coincide con la búsqueda.'
          }
        />
      ) : (
        <DataTable
          caption="Miembros del tenant"
          columns={columns}
          rows={filtered}
          rowKey={(row) => row.user_id}
        />
      )}
    </Card>
  );
}
