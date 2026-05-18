import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { InviteMemberForm } from './components/InviteMemberForm.jsx';
import { TeamTable } from './components/TeamTable.jsx';
import { useTeamData } from './hooks/useTeamData.js';
import { roleCounts } from './teamData.js';
import styles from './TeamModule.module.css';

const ROLE_TILES = [
  { key: 'owner', label: 'Owner' },
  { key: 'admin', label: 'Admin' },
  { key: 'manager', label: 'Manager' },
  { key: 'agent', label: 'Agent' },
  { key: 'viewer', label: 'Viewer' },
  { key: 'pending', label: 'Pendientes' },
];

/**
 * UI-007.13 — Config · Equipo.
 *
 * Redesign of the legacy `TeamModule` (325 LOC) into a feature with an
 * orchestrator + `useTeamData` hook + pure `teamData.js` + `TeamTable`
 * (DataTable with avatars, role badges, role-change select, revoke) and
 * `InviteMemberForm` (Modal). Member CRUD + the owner-role guards + the Auth0
 * invitation flow are preserved verbatim. Gated by `team.write` (RW); the
 * backend remains the authority.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/21 _ Config · Equipo.html`.
 * Declared difference: the HTML's per-member "MFA" column and the "N sin MFA"
 * header badge are not exposed by `listTenantMembers` — they are deferred; no
 * data is fabricated.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function TeamModule({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useTeamData({ session, tenant });
  const counts = roleCounts(state.members);

  return (
    <RequirePermission permissions={permissions} capability="team.write" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Configuración"
          title={module?.label || 'Equipo'}
          description="Miembros del negocio con acceso al panel. El acceso se verifica en cada acción contra el rol asignado."
          actions={
            <button
              type="button"
              className={styles.primaryButton}
              onClick={actions.openInvite}
              disabled={!state.tenantId}
            >
              Invitar miembro
            </button>
          }
        />

        {!state.auth0Enabled ? (
          <AlertBanner
            tone="warning"
            title="Auth0 Management API no está habilitada"
            description="Los cambios se reflejarán en el próximo login del usuario; sincroniza manualmente desde el dashboard de Auth0 si es necesario."
          />
        ) : null}

        {state.notice ? (
          <AlertBanner
            tone={state.notice.type === 'error' ? 'danger' : 'success'}
            title={state.notice.text}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissNotice}
              >
                Cerrar
              </button>
            }
          />
        ) : null}

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para gestionar su equipo."
            />
          </Card>
        ) : (
          <>
            <div className={styles.tileGrid}>
              {ROLE_TILES.map((tile) => (
                <div key={tile.key} className={styles.tile}>
                  <span className={styles.tileLabel}>{tile.label}</span>
                  <strong className={styles.tileValue}>{counts[tile.key]}</strong>
                </div>
              ))}
            </div>
            <TeamTable
              members={state.members}
              isLoading={state.isLoading}
              isBusy={state.isBusy}
              isOwner={state.isOwner}
              onChangeRole={actions.changeRole}
              onRemove={actions.removeMember}
            />
          </>
        )}

        <InviteMemberForm
          open={state.inviteOpen}
          inviteForm={state.inviteForm}
          isBusy={state.isBusy}
          isOwner={state.isOwner}
          tenantId={state.tenantId}
          onChange={actions.setInviteForm}
          onSubmit={actions.invite}
          onClose={actions.closeInvite}
        />
      </section>
    </RequirePermission>
  );
}
