/**
 * Auth0 Post-Login Action — MFA challenge para roles privilegiados.
 *
 * Si el user tiene rol admin/owner/platform_owner y NO completo MFA
 * en el factor de autenticacion, forzamos:
 *   - challengeWithAny(enrolled) si ya tiene factor enrolado
 *   - enrollWith({type:'otp'}) si es primer login (setup interactivo)
 *
 * Cargado desde scripts/configure-auth0.sh via cat (sin heredoc — bash 3.2
 * de macOS tira "bad substitution" en heredocs JS embebidos).
 *
 * Variables disponibles en el Action context:
 *   event.authorization.roles          - lista de roles del user
 *   event.authentication.methods       - factores ya completados este login
 *   event.user.enrolledFactors         - factores enrolados (confirmed)
 *   api.authentication.challengeWith*  - forzar verificacion de factor
 *   api.authentication.enrollWith*     - forzar enrollment de factor nuevo
 *
 * NOTA: este archivo es JS puro pero NO se ejecuta en tu maquina — se
 * uploadea a Auth0 como source del Action. Auth0 lo runa server-side
 * en su runtime Node.js (sandbox).
 */
exports.onExecutePostLogin = async (event, api) => {
  const privilegedRoles = new Set(['admin', 'owner', 'platform_owner']);
  const roles = (event.authorization && event.authorization.roles) || [];
  const isPrivileged = roles.some(function (r) {
    return privilegedRoles.has(r);
  });
  if (!isPrivileged) return;

  const methods = (event.authentication && event.authentication.methods) || [];
  const hasMfa = methods.some(function (m) {
    return m.name === 'mfa';
  });
  if (hasMfa) return;

  const enrolled = ((event.user && event.user.enrolledFactors) || [])
    .filter(function (f) {
      return f && f.status === 'confirmed';
    })
    .map(function (f) {
      return { type: f.type };
    });

  if (enrolled.length > 0) {
    api.authentication.challengeWithAny(enrolled);
  } else {
    api.authentication.enrollWith({ type: 'otp' });
  }
};
