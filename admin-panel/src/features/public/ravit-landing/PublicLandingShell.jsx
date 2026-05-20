/**
 * Shell público con tabs por producto (Personajes AI · Chatbot AI ·
 * Gestión Documental AI). Tokens canónicos en `ravit-tokens.css` (scoped
 * al data-testid del shell). Los tres tabs consumen las mismas vars
 * `--ra-*` y el mismo módulo CSS compartido `landing-shared.module.css`.
 *
 * Labels = acción del producto, no carpeta interna:
 *   - Personajes AI       → casting de personajes virtuales (Ravit)
 *   - Chatbot AI          → asistente conversacional (CopilotoIA legacy)
 *   - Gestión Documental AI → procesamiento de documentos con IA
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { adminPath } from '../../../services/adminSession.js';
import { Landing } from '../landing/Landing.jsx';
import { DocumentsLanding } from './DocumentsLanding.jsx';
import { RavitAgentPulse } from './RavitAgentPulse.jsx';
import { RavitMark } from './assets/illustrations.jsx';
import styles from './PublicLandingShell.module.css';
import './ravit-tokens.css';


const TABS = [
  { id: 'ravit',      label: 'Personajes AI',        href: '/' },
  { id: 'copiloto',   label: 'Chatbot AI',           href: '/copiloto' },
  { id: 'documentos', label: 'Gestión Documental AI', href: '/documentos' },
];

const DEFAULT_LOGIN_HREF = adminPath('/admin/login');


export function PublicLandingShell({
  activeTab = 'ravit',
  demoMailto = 'mailto:demo@ravit.studio',
  loginHref = DEFAULT_LOGIN_HREF,
  onDemoRequest,
}) {
  const [demoModalOpen, setDemoModalOpen] = useState(false);

  return (
    <div data-testid="public-landing-shell" className={styles.shell}>
      <header role="banner" className={styles.header}>
        <Link to="/" className={styles.brand} aria-label="Ravit Studio">
          <RavitMark size={36} />
          <span className={styles.brandText}>
            Ravit <span className={styles.brandSub}>STUDIO</span>
          </span>
        </Link>

        <nav aria-label="Tabs principales" className={styles.tabs}>
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <Link
                key={tab.id}
                to={tab.href}
                aria-current={isActive ? 'page' : undefined}
                className={isActive ? styles.tabActive : styles.tabIdle}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        <div className={styles.headerCtas}>
          <a href={loginHref} className={styles.btnText}>Entrar</a>
          <button
            type="button"
            onClick={() => setDemoModalOpen(true)}
            className={styles.btnPrimary}
          >
            Empezar gratis <span aria-hidden="true">→</span>
          </button>
        </div>
      </header>

      <main role="main">
        {activeTab === 'ravit' && (
          <RavitAgentPulse demoMailto={demoMailto} loginHref={loginHref} />
        )}
        {activeTab === 'copiloto' && (
          <Landing embedded demoMailto={demoMailto} loginHref={loginHref} />
        )}
        {activeTab === 'documentos' && (
          <DocumentsLanding demoMailto={demoMailto} loginHref={loginHref} />
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
      className={styles.modalBackdrop}
    >
      <form onSubmit={handleSubmit} className={styles.modalCard}>
        <h2 id="demo-dialog-title" className={styles.modalTitle}>Empezar gratis</h2>
        <label className={styles.field}>
          <span>Nombre</span>
          <input
            required
            value={form.name}
            onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
          />
        </label>
        <label className={styles.field}>
          <span>Email</span>
          <input
            required type="email"
            value={form.email}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
          />
        </label>
        <label className={styles.field}>
          <span>Empresa (opcional)</span>
          <input
            value={form.company}
            onChange={(e) => setForm((p) => ({ ...p, company: e.target.value }))}
          />
        </label>
        <div className={styles.modalActions}>
          <button type="button" onClick={onClose} className={styles.btnText}>Cancelar</button>
          <button type="submit" className={styles.btnPrimary}>Enviar</button>
        </div>
      </form>
    </div>
  );
}
