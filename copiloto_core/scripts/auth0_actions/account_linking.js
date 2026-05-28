/**
 * Auth0 Post-Login Action — Account Linking automatico por email verificado.
 *
 * Si un user se loguea con un proveedor (email/password, Google, etc.) y
 * existe OTRO user en Auth0 con el mismo email verified=true, linkeamos
 * automaticamente: el current se vuelve secondary del user mas antiguo
 * (primary). Eso evita identidades duplicadas en Auth0 y rompe el flujo
 * de M57 reconciliation (que busca por email).
 *
 * Cargado desde scripts/configure-auth0.sh via cat (sin heredoc — bash 3.2
 * de macOS tira "bad substitution" en heredocs JS embebidos).
 *
 * Variables disponibles:
 *   event.user.email                   - email del current
 *   event.user.email_verified          - bool
 *   event.user.user_id                 - "auth0|abc..."
 *   event.secrets.AUTH0_DOMAIN         - inyectado por el script
 *   event.secrets.AUTH0_M2M_CLIENT_ID  - idem
 *   event.secrets.AUTH0_M2M_CLIENT_SECRET - idem
 *
 * Requiere scope en el Action M2M: read:users + update:users.
 */
const ManagementClient = require('auth0').ManagementClient;

exports.onExecutePostLogin = async (event, api) => {
  if (!event.user.email || event.user.email_verified !== true) return;
  // Skip si ya es secondary (no tiene "|" en user_id).
  if (event.user.user_id && event.user.user_id.indexOf('|') === -1) return;

  const mgmt = new ManagementClient({
    domain: event.secrets.AUTH0_DOMAIN,
    clientId: event.secrets.AUTH0_M2M_CLIENT_ID,
    clientSecret: event.secrets.AUTH0_M2M_CLIENT_SECRET,
  });

  let candidates;
  try {
    candidates = await mgmt.usersByEmail.getByEmail({ email: event.user.email });
  } catch (e) {
    console.log('account-linking: getByEmail error', e.message);
    return;
  }

  const list = candidates.data || candidates || [];
  const verifiedOthers = list.filter(function (u) {
    return u.user_id !== event.user.user_id && u.email_verified === true;
  });
  if (verifiedOthers.length === 0) return;

  // Primary = mas viejo. Preserva el user_id historico en audit logs.
  verifiedOthers.sort(function (a, b) {
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
  const primary = verifiedOthers[0];

  try {
    const parts = event.user.user_id.split('|');
    const secondaryProvider = parts[0];
    const secondaryUserId = parts[1];
    await mgmt.users.link(
      { id: primary.user_id },
      { provider: secondaryProvider, user_id: secondaryUserId },
    );
    console.log(
      'account-linking: linked',
      event.user.user_id,
      'into',
      primary.user_id,
    );
  } catch (e) {
    console.log('account-linking: link failed', e.message);
  }
};
