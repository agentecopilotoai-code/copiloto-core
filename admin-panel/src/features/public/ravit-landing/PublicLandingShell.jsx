/**
 * UI-INFLU-016 — Shell público con tabs (Ravit Agent · Pulse / CopilotoIA).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { adminPath } from '../../../services/adminSession.js';
import { Landing } from '../landing/Landing.jsx';
import { RavitAgentPulse } from './RavitAgentPulse.jsx';


const TABS = [
  { id: 'ravit', label: 'Ravit Agent · Pulse', href: '/' },
  { id: 'copiloto', label: 'CopilotoIA', href: '/copiloto' },
];

// Misma ruta de Auth0 que usa el Landing histórico (LandingHeader.jsx);
// `/login` en el SPA solo redirige a `/`, así que un href directo
// dispararía un loop. El flow real vive en el backend en `/admin/login`.
const DEFAULT_LOGIN_HREF = adminPath('/admin/login');


export function PublicLandingShell({
  activeTab = 'ravit',
  demoMailto = 'mailto:demo@ravit.studio',
  loginHref = DEFAULT_LOGIN_HREF,
  onDemoRequest,
}) {
  const [demoModalOpen, setDemoModalOpen] = useState(false);

  return (
    <div data-testid="public-landing-shell" style={{
      background: 'var(--ra-bg, #F1EDE3)',
      minHeight: '100vh',
    }}>
      <header role="banner" style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: 'var(--space-2) var(--space-4)',
        borderBottom: '1px solid rgba(15, 122, 63, 0.15)',
      }}>
        <Link to="/" style={{ fontWeight: 800, textDecoration: 'none', color: 'inherit' }}>
          Ravit
        </Link>
        <nav aria-label="Tabs principales">
          <ul style={{ display: 'flex', gap: 'var(--space-2)', listStyle: 'none', margin: 0, padding: 0 }}>
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <li key={tab.id}>
                  <Link
                    to={tab.href}
                    aria-current={isActive ? 'page' : undefined}
                    style={{
                      padding: '6px 12px',
                      borderRadius: 6,
                      textDecoration: 'none',
                      color: isActive ? '#fff' : 'inherit',
                      background: isActive ? 'var(--ra-accent, #0F7A3F)' : 'transparent',
                      fontWeight: 600,
                    }}
                  >{tab.label}</Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
          <button
            type="button"
            onClick={() => setDemoModalOpen(true)}
            style={{
              padding: '6px 14px',
              background: 'var(--ra-brand, #2DBB6A)',
              color: '#fff', border: 'none', borderRadius: 6,
              fontWeight: 600, cursor: 'pointer',
            }}
          >Solicitar demo</button>
          <a href={loginHref} style={{
            padding: '6px 14px',
            background: 'transparent',
            border: '1px solid var(--ra-text, #1B2542)',
            color: 'var(--ra-text, #1B2542)',
            borderRadius: 6, textDecoration: 'none', fontWeight: 600,
          }}>Iniciar sesión</a>
        </div>
      </header>

      <main role="main">
        {activeTab === 'ravit' ? (
          <RavitAgentPulse demoMailto={demoMailto} loginHref={loginHref} />
        ) : (
          <Landing embedded demoMailto={demoMailto} loginHref={loginHref} />
        )}
      </main>

      {demoModalOpen && (
        <DemoRequestModal
          onClose={() => setDemoModalOpen(false)}
          onSubmit={async (data) => {
            await onDemoRequest?.(data);
            setDemoModalOpen(false);
          }}
        />
      )}
    </div>
  );
}


function DemoRequestModal({ onClose, onSubmit }) {
  const [form, setForm] = useState({ name: '', email: '', company: '' });
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(form);
  };
  return (
    <div
      role="dialog"
      aria-labelledby="demo-dialog-title"
      aria-modal="true"
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <form onSubmit={handleSubmit} style={{
        background: '#fff', padding: 'var(--space-4)', borderRadius: 12,
        maxWidth: 400, width: '90%',
      }}>
        <h2 id="demo-dialog-title">Solicitar demo</h2>
        <label style={{ display: 'block' }}>
          <span>Nombre</span>
          <input
            required
            value={form.name}
            onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
            style={{ width: '100%' }}
          />
        </label>
        <label style={{ display: 'block', marginTop: 'var(--space-1)' }}>
          <span>Email</span>
          <input
            required type="email"
            value={form.email}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
            style={{ width: '100%' }}
          />
        </label>
        <label style={{ display: 'block', marginTop: 'var(--space-1)' }}>
          <span>Empresa</span>
          <input
            value={form.company}
            onChange={(e) => setForm((p) => ({ ...p, company: e.target.value }))}
            style={{ width: '100%' }}
          />
        </label>
        <div style={{ display: 'flex', gap: 'var(--space-1)', justifyContent: 'flex-end', marginTop: 'var(--space-3)' }}>
          <button type="button" onClick={onClose}>Cancelar</button>
          <button type="submit">Enviar</button>
        </div>
      </form>
    </div>
  );
}
