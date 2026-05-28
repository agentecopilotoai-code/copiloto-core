/**
 * Auth0 Post-Login Action — Custom Claims namespaced.
 *
 * Emite claims con el namespace de CopilotoIA en id_token + access_token:
 *   - roles, permissions, tenant_id, tenant_slug
 *   - support_mode (cross-tenant flag para platform_owner)
 *   - email + email_verified (M60/A-003 — fix hijack del header)
 *   - mfa_verified + amr (MFA enforcement del BFF + Core)
 *
 * Cargado desde scripts/configure-auth0.sh. El placeholder
 * __CLAIMS_NAMESPACE__ se sustituye con sed por el valor real
 * de $CLAIMS_NAMESPACE antes de subirlo a Auth0 (single source of
 * truth para el namespace).
 */
exports.onExecutePostLogin = async (event, api) => {
  const namespace = '__CLAIMS_NAMESPACE__';
  const appMetadata = event.user.app_metadata || {};
  const roles = (event.authorization && event.authorization.roles) || [];
  const permissions = (event.authorization && event.authorization.permissions) || [];
  const tenantId = appMetadata.tenant_id || appMetadata.default_tenant_id;

  api.idToken.setCustomClaim(`${namespace}/roles`, roles);
  api.accessToken.setCustomClaim(`${namespace}/roles`, roles);
  api.accessToken.setCustomClaim(`${namespace}/permissions`, permissions);

  // M60/A-003 — email en el ACCESS_TOKEN como claim namespaced.
  // Auth0 lo pone en id_token + userinfo por default pero NO en access_token,
  // entonces el Core caia al fallback de header `x-admin-user-email` (SPOOFABLE).
  // Con este claim el Core lee el email del JWT firmado y no necesita el header.
  if (event.user && event.user.email) {
    api.accessToken.setCustomClaim(`${namespace}/email`, event.user.email);
    api.accessToken.setCustomClaim(
      `${namespace}/email_verified`,
      event.user.email_verified === true,
    );
  }

  if (tenantId) {
    api.idToken.setCustomClaim(`${namespace}/tenant_id`, tenantId);
    api.accessToken.setCustomClaim(`${namespace}/tenant_id`, tenantId);
  }

  if (appMetadata.tenant_slug) {
    api.idToken.setCustomClaim(`${namespace}/tenant_slug`, appMetadata.tenant_slug);
    api.accessToken.setCustomClaim(`${namespace}/tenant_slug`, appMetadata.tenant_slug);
  }

  if (appMetadata.support_mode === true) {
    api.accessToken.setCustomClaim(`${namespace}/support_mode`, true);
  }

  // Propagar AMR (Authentication Methods References) para que la API y el
  // Admin Panel verifiquen si el login incluyo MFA. Auth0 rellena
  // event.authentication.methods con { name: 'mfa', ... } cuando el user
  // completa un segundo factor.
  const methods = (event.authentication && event.authentication.methods) || [];
  const mfaCompleted = methods.some(function (m) {
    return m.name === 'mfa';
  });
  const amr = methods.map(function (m) { return m.name; }).filter(Boolean);
  if (amr.length > 0) {
    api.idToken.setCustomClaim('amr', amr);
  }
  api.idToken.setCustomClaim(`${namespace}/mfa_verified`, mfaCompleted);
  api.accessToken.setCustomClaim(`${namespace}/mfa_verified`, mfaCompleted);
};
