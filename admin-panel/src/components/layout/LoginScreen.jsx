import { adminPath } from '../../services/adminSession.js';

export function LoginScreen({ error }) {
  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="eyebrow">Admin Panel MVP</p>
        <h1>CopilotoIA</h1>
        <p>Ingresa con Auth0/OIDC para administrar tenants, canales, conocimiento y operación humana.</p>
        <a className="primary-action" href={adminPath('/admin/login')}>
          Iniciar sesión con Auth0
        </a>
        <p className="hint">
          {error?.message || (
            <>
              Usa la aplicación <strong>copilotoia-admin-web</strong> generada por{' '}
              <code>scripts/configure-auth0.sh</code>.
            </>
          )}
        </p>
      </section>
    </main>
  );
}
