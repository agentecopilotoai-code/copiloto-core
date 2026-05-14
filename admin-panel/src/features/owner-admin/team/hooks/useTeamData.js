import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  inviteTenantMember,
  listTenantMembers,
  removeTenantMember,
  updateTenantMemberRole,
} from '../../../../services/coreApi.js';
import { callerIsOwner, emptyInviteForm, highestRole } from '../teamData.js';

/**
 * Data layer for the Config · Equipo view. Owns the member list, the Auth0
 * status flag and the invite form, plus every mutation handler extracted
 * verbatim from the legacy `TeamModule` (including the owner-role guards and
 * the native confirm prompts).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token + profile)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useTeamData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [members, setMembers] = useState([]);
  const [auth0Enabled, setAuth0Enabled] = useState(false);
  const [notice, setNotice] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [inviteForm, setInviteForm] = useState(emptyInviteForm);
  const [inviteOpen, setInviteOpen] = useState(false);

  const isOwner = useMemo(
    () => callerIsOwner(session?.profile?.roles, tenant?.roles),
    [session?.profile?.roles, tenant?.roles],
  );

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    setIsLoading(true);
    setNotice(null);
    try {
      const result = await listTenantMembers(session, tenantId);
      setMembers(result?.members || []);
      setAuth0Enabled(Boolean(result?.auth0_management_enabled));
    } catch (error) {
      setNotice({
        type: 'error',
        text: error.message || 'No se pudo cargar el equipo del tenant.',
      });
    } finally {
      setIsLoading(false);
    }
  }, [session, tenantId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const actions = {
    setInviteForm,
    dismissNotice: () => setNotice(null),
    openInvite: () => {
      setInviteForm(emptyInviteForm());
      setInviteOpen(true);
    },
    closeInvite: () => setInviteOpen(false),
    async invite() {
      if (!tenantId) return;
      if (!inviteForm.email.trim()) {
        setNotice({ type: 'error', text: 'Ingresa el email del nuevo miembro.' });
        return;
      }
      setIsBusy(true);
      setNotice(null);
      try {
        const result = await inviteTenantMember(session, tenantId, {
          email: inviteForm.email.trim(),
          display_name: inviteForm.display_name.trim() || undefined,
          role: inviteForm.role,
        });
        setInviteForm(emptyInviteForm());
        setInviteOpen(false);
        // TASK-0085 / BUG06: the API no longer returns a password-change ticket
        // URL — Auth0 emails the invitation directly to the new user. The UI
        // must NOT display, copy or persist any such link.
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
    },
    async changeRole(member, nextRole) {
      if (!tenantId) return;
      if (nextRole === 'owner' && !isOwner) {
        setNotice({ type: 'error', text: 'Solo un owner puede asignar el rol owner.' });
        return;
      }
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      const confirmed = window.confirm(
        `¿Cambiar el rol de ${member.email} de "${highestRole(member.roles)}" a "${nextRole}"?`,
      );
      if (!confirmed) return;
      setIsBusy(true);
      setNotice(null);
      try {
        await updateTenantMemberRole(session, tenantId, member.user_id, nextRole);
        setNotice({
          type: 'success',
          text: 'Rol actualizado. El próximo JWT del usuario reflejará el cambio.',
        });
        await refresh();
      } catch (error) {
        setNotice({ type: 'error', text: error.message || 'No se pudo actualizar el rol.' });
      } finally {
        setIsBusy(false);
      }
    },
    async removeMember(member) {
      if (!tenantId) return;
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      const confirmed = window.confirm(
        `¿Revocar el acceso de ${member.email} a este tenant? Esta acción no se puede deshacer.`,
      );
      if (!confirmed) return;
      setIsBusy(true);
      setNotice(null);
      try {
        await removeTenantMember(session, tenantId, member.user_id);
        setNotice({ type: 'success', text: 'Acceso revocado.' });
        await refresh();
      } catch (error) {
        setNotice({ type: 'error', text: error.message || 'No se pudo revocar el acceso.' });
      } finally {
        setIsBusy(false);
      }
    },
  };

  return {
    state: {
      tenantId,
      members,
      auth0Enabled,
      notice,
      isLoading,
      isBusy,
      inviteForm,
      inviteOpen,
      isOwner,
    },
    actions,
  };
}
